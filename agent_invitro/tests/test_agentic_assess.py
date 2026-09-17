"""十分性評価のパース・分岐判定・結果蓄積のテスト（ADR-0088 / N-8.6 / DoD 11）。

Bedrock・MCP へ接続せず、純関数として切り出した処理を検証する。
- llm_tasks.assess.parse_assessment: 素の JSON / コードフェンス付き / 前置き付き / 不正出力。
- llm_tasks.assess.SufficiencyAssessorBedrock.assess: 呼び出し失敗・パース失敗時の縮退（F-6.3.8）。
- graph.agentic_search._decide: F-6.3.4 の3分岐と F-6.3.6（同一クエリの抑止）。
- knowledge.merge_results: 重複排除（id 優先, 無ければ title）と件数上限（F-6.3.7）。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_invitro.llm_tasks.assess import (
    SufficiencyAssessor,
    SufficiencyAssessorBedrock,
    parse_assessment,
)
from agent_invitro.graph.agentic_search import (
    OUTCOME_ANSWER,
    OUTCOME_CLARIFY,
    OUTCOME_SEARCH,
    _decide,
)
from agent_invitro.knowledge import merge_results


# --- parse_assessment ----------------------------------------------------
def test_parse_plain_json():
    parsed = parse_assessment(
        '{"sufficient": false, "missing": "手順の詳細", "next_query": "積算 手順"}'
    )
    assert parsed == {
        "sufficient": False,
        "missing": "手順の詳細",
        "next_query": "積算 手順",
    }


def test_parse_with_code_fence_and_preamble():
    raw = '判定結果は以下の通りです。\n```json\n{"sufficient": true, "missing": "", "next_query": ""}\n```'
    parsed = parse_assessment(raw)
    assert parsed == {"sufficient": True, "missing": "", "next_query": ""}


def test_parse_accepts_string_boolean():
    parsed = parse_assessment('{"sufficient": "true", "missing": null, "next_query": null}')
    assert parsed == {"sufficient": True, "missing": "", "next_query": ""}


def test_parse_returns_none_for_unparsable():
    assert parse_assessment("十分だと思います。") is None
    assert parse_assessment("") is None
    # JSON ではあるがオブジェクトでない / sufficient が無い場合も None。
    assert parse_assessment("[1, 2, 3]") is None
    assert parse_assessment('{"missing": "x"}') is None


# --- assess() のフォールバック（F-6.3.8）---------------------------------
class _StubAssessor(SufficiencyAssessorBedrock):
    """boto3 クライアントを作らずに _invoke だけ差し替えるスタブ。

    SufficiencyAssessorBedrock 経由で SufficiencyAssessor（ADR-0091 決定3）を継承しており、
    「例外を送出しない」「3キーを返す」という契約をここで担保する。
    """

    def __init__(self, behavior):
        self._behavior = behavior  # 呼ばれたら文字列を返すか例外を送出する callable

    def _invoke(self, system, user_content):  # noqa: D102
        return self._behavior(user_content)


def test_assess_falls_back_to_sufficient_on_invoke_error():
    def boom(_):
        raise RuntimeError("bedrock down")

    result = _StubAssessor(boom).assess("質問", [], [])
    assert result == {"sufficient": True, "missing": "", "next_query": ""}


def test_assess_falls_back_to_sufficient_on_parse_error():
    result = _StubAssessor(lambda _: "よくわかりません").assess("質問", [], [])
    assert result == {"sufficient": True, "missing": "", "next_query": ""}


def test_assess_passes_question_results_and_tried_queries_to_prompt():
    captured = {}

    def capture(user_content):
        captured["prompt"] = user_content
        return '{"sufficient": true, "missing": "", "next_query": ""}'

    _StubAssessor(capture).assess(
        "積算の操作方法", [{"title": "T1", "content": "C1"}], ["積算 操作"]
    )
    assert "積算の操作方法" in captured["prompt"]
    assert "T1" in captured["prompt"] and "C1" in captured["prompt"]
    assert "積算 操作" in captured["prompt"]


# --- _decide（F-6.3.4 / F-6.3.6）----------------------------------------
_SUFFICIENT = {"sufficient": True, "missing": "", "next_query": ""}


def _insufficient(next_query: str = "別の言い方") -> dict:
    return {"sufficient": False, "missing": "不足", "next_query": next_query}


def test_decide_sufficient_goes_to_answer():
    assert _decide(_SUFFICIENT, 1, ["q1"], [], max_iterations=2) == (OUTCOME_ANSWER, "")


def test_decide_insufficient_under_limit_searches_again():
    outcome, next_query = _decide(
        _insufficient(), iteration=1, tried_queries=["q1"], results=[], max_iterations=2
    )
    assert (outcome, next_query) == (OUTCOME_SEARCH, "別の言い方")


def test_decide_at_limit_with_results_answers():
    outcome, _ = _decide(
        _insufficient(), iteration=2, tried_queries=["q1", "q2"],
        results=[{"id": 1}], max_iterations=2,
    )
    assert outcome == OUTCOME_ANSWER


def test_decide_at_limit_without_results_clarifies():
    outcome, _ = _decide(
        _insufficient(), iteration=2, tried_queries=["q1", "q2"],
        results=[], max_iterations=2,
    )
    assert outcome == OUTCOME_CLARIFY


def test_decide_empty_next_query_stops_the_loop():
    outcome, _ = _decide(
        _insufficient(""), iteration=1, tried_queries=["q1"], results=[], max_iterations=2
    )
    assert outcome == OUTCOME_CLARIFY


def test_decide_duplicate_next_query_stops_the_loop():
    """F-6.3.6: 既に試したクエリと同一なら再検索しない（前後空白は無視して比較）。"""
    outcome, _ = _decide(
        _insufficient(" q1 "), iteration=1, tried_queries=["q1"],
        results=[{"id": 1}], max_iterations=2,
    )
    assert outcome == OUTCOME_ANSWER


# --- merge_results（F-6.3.7）--------------------------------------------
def test_merge_results_dedupes_by_id_then_title():
    acc = [{"id": 1, "title": "A"}, {"title": "B"}]
    merged = merge_results(acc, [{"id": 1, "title": "A"}, {"title": "B"}, {"id": 2}], limit=6)
    assert merged == [{"id": 1, "title": "A"}, {"title": "B"}, {"id": 2}]


def test_merge_results_respects_limit():
    merged = merge_results([{"id": 1}], [{"id": 2}, {"id": 3}, {"id": 4}], limit=3)
    assert [r["id"] for r in merged] == [1, 2, 3]
