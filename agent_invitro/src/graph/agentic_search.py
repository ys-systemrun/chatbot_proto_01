"""Agentic 探索ループの StateGraph（ADR-0088 決定1 / 要件定義書 5.3・10章）。

`search`（search_knowledge 1回）と `assess`（十分性評価 LLM 1回）の2ノードを条件付きエッジで
周回させる。`condense`・`select_tags` はグラフの前段（usecases/ask_agentic.py）で1回だけ実行し、
初期 State へ入れる（周回に入らない, ADR-0088 決定1・決定4）。`generate` / `clarify` はグラフの
終端ではなくユースケース層で行い、グラフは「どちらへ進むか」を `outcome` として返すに留める
（テスト容易性を優先, 要件定義書10章）。

`create_react_agent`（ADR-0022, graph/agent.py）は使わない。必須ステップは決定論的に固定し、
「もう一度探すか／何で探すか」の判断のみを LLM に委ねる（ADR-0088 決定）。
"""

from __future__ import annotations

import logging
from typing import TypedDict

import anyio.to_thread
from langgraph.graph import END, StateGraph

from ..knowledge import merge_results, search_knowledge
from ..llm_tasks.assess import SufficiencyAssessor

logger = logging.getLogger(__name__)

# assess ノードが決める次の行き先。"search" のときのみ周回を続ける。
OUTCOME_SEARCH = "search"
OUTCOME_ANSWER = "answer"
OUTCOME_CLARIFY = "clarify"


class AgenticSearchState(TypedDict, total=False):
    """1リクエスト処理中にのみ存在する探索ループの状態（N-8.4: レスポンスにも DB にも残さない）。"""

    text: str                   # 今回の発話（req.text）
    condensed_query: str        # 言い換え質問（ADR-0085）。十分性評価の「ユーザーの質問」に使う
    tags: list[str]             # select_tags が選定したタグ名（全周回で共通, ADR-0088 決定4）
    current_query: str          # この周回で search_knowledge へ渡すクエリ
    tried_queries: list[str]    # これまでに試したクエリ（重複検索の抑止, F-6.3.6）
    results: list[dict]         # 全周回の検索結果（重複排除済み, F-6.3.7）
    iteration: int              # 実行済みの周回数
    assessment: dict            # 最後の十分性評価 {"sufficient", "missing", "next_query"}
    outcome: str                # OUTCOME_* のいずれか


def build_agentic_search_graph(
    search_tool,
    assessor: SufficiencyAssessor,
    *,
    max_iterations: int = 2,
    top_k: int = 3,
    conversation_id: str = "",
):
    """探索ループのグラフを構築してコンパイル済みグラフを返す。

    Args:
        search_tool: Knowledge MCP の `search_knowledge` ツール（`ainvoke` を持つ）。
        assessor: 十分性評価器（`llm_tasks.assess.SufficiencyAssessor` の実装, ADR-0091 決定3）。
                  `assess()` は同期・例外を送出しない契約のため、戻り値のみで分岐でき、
                  呼び出しはスレッドプール経由で行う。
        max_iterations: 周回数の上限（F-6.3.5, 既定は設定値 AGENTIC_MAX_ITERATIONS）。
        top_k: 1周回あたりの search_knowledge の top_k（AGENTIC_SEARCH_TOP_K）。
        conversation_id: ログに含める会話ID（F-6.6.1）。
    """
    result_limit = max(1, top_k * max_iterations)

    async def search(state: AgenticSearchState) -> dict:
        """search_knowledge を1回呼び、結果を重複排除しつつ蓄積する（F-6.3.1 / F-6.3.7）。"""
        query = state["current_query"]
        iteration = state.get("iteration", 0) + 1
        tags = state.get("tags", [])

        try:
            hits = await search_knowledge(search_tool, query, tags, top_k=top_k)
        except Exception:
            # F-6.3.9: この周回は0件としてループを継続する（500 にはしない）。
            logger.exception(
                "[%s] iter=%d search_knowledge failed query=%r",
                conversation_id, iteration, query,
            )
            hits = []

        results = merge_results(state.get("results", []), hits, result_limit)
        logger.info(
            "[%s] iter=%d search query=%r tags=%d hits=%d accumulated=%d",
            conversation_id, iteration, query, len(tags), len(hits), len(results),
        )
        return {
            "iteration": iteration,
            "results": results,
            "tried_queries": [*state.get("tried_queries", []), query],
        }

    async def assess(state: AgenticSearchState) -> dict:
        """十分性を評価し、次の行き先（outcome）と次のクエリを決める（F-6.3.2〜F-6.3.6）。

        分岐の判定をノード内で行い、条件付きエッジは `outcome` を読むだけにする
        （LangGraph のルーター関数は State を書き換えられないため）。
        """
        iteration = state.get("iteration", 0)
        results = state.get("results", [])
        tried = state.get("tried_queries", [])

        # boto3 は同期 API のためスレッドプールで実行する（N-8.5）。
        assessment = await anyio.to_thread.run_sync(
            assessor.assess, state["condensed_query"], results, tried
        )
        logger.info(
            "[%s] iter=%d assess sufficient=%s missing=%r next_query=%r",
            conversation_id,
            iteration,
            assessment.get("sufficient"),
            assessment.get("missing", ""),
            assessment.get("next_query", ""),
        )

        outcome, next_query = _decide(
            assessment, iteration, tried, results, max_iterations
        )
        update: dict = {"assessment": assessment, "outcome": outcome}
        if outcome == OUTCOME_SEARCH:
            update["current_query"] = next_query
        return update

    def route_after_assess(state: AgenticSearchState) -> str:
        return OUTCOME_SEARCH if state.get("outcome") == OUTCOME_SEARCH else END

    graph = StateGraph(AgenticSearchState)
    graph.add_node("search", search)
    graph.add_node("assess", assess)
    graph.set_entry_point("search")
    graph.add_edge("search", "assess")
    graph.add_conditional_edges(
        "assess", route_after_assess, {OUTCOME_SEARCH: "search", END: END}
    )
    return graph.compile()


def _decide(
    assessment: dict,
    iteration: int,
    tried_queries: list[str],
    results: list[dict],
    max_iterations: int,
) -> tuple[str, str]:
    """F-6.3.4 の3分岐を判定して `(outcome, next_query)` を返す。

    Bedrock・MCP に接続せず単体テストできる純関数として切り出す（N-8.6）。

    1. `sufficient=true` → 回答生成へ。
    2. `sufficient=false` かつ 周回数 < 上限 かつ `next_query` が非空かつ未試行 → 再検索。
    3. それ以外（上限到達 / `next_query` が空 / 既に試したクエリと同一, F-6.3.6）
       → 蓄積結果が1件以上あれば回答生成へ、0件なら逆質問へ。
    """
    if assessment.get("sufficient"):
        return OUTCOME_ANSWER, ""

    next_query = str(assessment.get("next_query") or "").strip()
    already_tried = {q.strip() for q in tried_queries}
    if iteration < max_iterations and next_query and next_query not in already_tried:
        return OUTCOME_SEARCH, next_query

    return (OUTCOME_ANSWER if results else OUTCOME_CLARIFY), ""
