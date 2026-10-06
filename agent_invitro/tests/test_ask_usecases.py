"""ユースケース層のテスト（ADR-0090 決定4 / N-8.6 / DoD 11）。

MCP・Bedrock へ接続せず、fake のツール・LLM クライアントで `/ask-pipeline`・`/ask-agentic` の
実処理を検証する。FastAPI のテストクライアントは使わない（ユースケース層は fastapi に依存
しない, F-6.7.4）。
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_invitro.clarify import FALLBACK_CLARIFICATION
from agent_invitro.llm_tasks.assess import (
    SufficiencyAssessor,
    SufficiencyAssessorBedrock,
)
from agent_invitro.main.api.schemas import Request, Summary
from agent_invitro.usecases.ask_agentic import ask_agentic
from agent_invitro.usecases.ask_pipeline import ask_pipeline


# --- fake なコンポーネント群 ----------------------------------------------
@dataclass
class FakeSettings:
    bedrock_chat_model_id: str = "fake-model"
    bedrock_region: str = "ap-northeast-1"
    tag_selector_max_tags: int = 3
    tag_selector_confidence_threshold: float = 0.0
    agentic_max_iterations: int = 2
    agentic_search_top_k: int = 3


class FakeSearchTool:
    """呼び出しごとに用意された結果を返す search_knowledge ツール。"""

    def __init__(self, responses: list[list[dict]]):
        self._responses = responses
        self.calls: list[dict] = []

    async def ainvoke(self, args: dict):
        self.calls.append(args)
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return {"results": self._responses[idx]}


class FakeTagsTool:
    def __init__(self, names: list[str] | None = None):
        self._names = names or ["タグA"]
        self.calls: list[dict] = []

    async def ainvoke(self, args: dict):
        self.calls.append(args)
        return {"selected": [{"name": n} for n in self._names]}


class FakeCondenser:
    def __init__(self, condensed: str | None = None):
        self._condensed = condensed

    def condense(self, text, messages, summary=""):
        return self._condensed or text


class FakeGenerator:
    def __init__(self):
        self.calls: list[tuple] = []

    def generate(self, context, question, summary="", history=None):
        self.calls.append((context, question, summary, history))
        return "回答本文", f"PROMPT<{context}>"


class FakeAssessor(SufficiencyAssessor):
    """周回ごとの評価結果を順に返す。尽きたら最後の値を返し続ける。"""

    def __init__(self, assessments: list[dict]):
        self._assessments = assessments
        self.calls: list[tuple] = []

    def assess(self, question, results, tried_queries):
        self.calls.append((question, list(results), list(tried_queries)))
        idx = min(len(self.calls) - 1, len(self._assessments) - 1)
        return self._assessments[idx]


class FailingAssessor(SufficiencyAssessorBedrock):
    """Bedrock 呼び出しが必ず失敗する実物の評価器（boto3 クライアントは作らない）。

    縮退（F-6.3.8）は SufficiencyAssessorBedrock.assess の内部で行われるため、fake ではなく
    実物のクラスの _invoke だけを差し替えて検証する。
    """

    def __init__(self):
        self.calls: list[tuple] = []

    def _invoke(self, system, user_content):
        self.calls.append((system, user_content))
        raise RuntimeError("bedrock down")


class FakeClarifier:
    def __init__(self, text: str = "どの画面で発生しましたか？"):
        self._text = text
        self.calls: list[tuple] = []

    def clarify(self, question, original_text, tried_queries, missing=""):
        self.calls.append((question, original_text, list(tried_queries), missing))
        return self._text, "CLARIFY_PROMPT"


class FakeSummarizer:
    def summarize(self, messages, previous):
        return "要約テキスト"


def build_components(**overrides) -> dict:
    components = {
        "settings": FakeSettings(),
        "search_tool": FakeSearchTool([[{"id": 1, "title": "T1", "content": "C1"}]]),
        "tags_tool": FakeTagsTool(),
        "summarizer": FakeSummarizer(),
        "generator": FakeGenerator(),
        "condenser": FakeCondenser(),
        "assessor": FakeAssessor([{"sufficient": True, "missing": "", "next_query": ""}]),
        "clarifier": FakeClarifier(),
    }
    components.update(overrides)
    return components


def build_request(text: str = "積算の操作方法を教えてください") -> Request:
    return Request(
        conversation_id="conv-1",
        text=text,
        messages=[],
        summary=Summary(content="", summarized_upto=0),
    )


SUFFICIENT = {"sufficient": True, "missing": "", "next_query": ""}


def insufficient(next_query: str = "積算 手順 別の言い方") -> dict:
    return {"sufficient": False, "missing": "手順の詳細", "next_query": next_query}


# --- /ask-pipeline -------------------------------------------------------
def test_ask_pipeline_builds_response():
    components = build_components()
    resp = asyncio.run(ask_pipeline(build_request(), components))

    assert resp.conversation_id == "conv-1"
    assert [m.order for m in resp.messages] == [1, 2]

    user, assistant = resp.messages
    assert user.role == "user"
    assert user.content == (
        "参考情報:\nQ: T1\nA: C1\n\n質問:\n積算の操作方法を教えてください"
    )
    assert assistant.role == "assistant"
    assert assistant.content == "回答本文"
    assert assistant.model == "fake-model"
    assert assistant.evaluation == 0
    # search_knowledge はちょうど1回（一本道パイプライン, ADR-0043）。
    assert len(components["search_tool"].calls) == 1
    assert components["search_tool"].calls[0]["tags"] == ["タグA"]


def test_ask_pipeline_issues_conversation_id_when_absent():
    req = build_request()
    req.conversation_id = None
    resp = asyncio.run(ask_pipeline(req, build_components()))
    assert resp.conversation_id


def test_ask_pipeline_continues_when_select_tags_fails():
    class BoomTagsTool:
        async def ainvoke(self, args):
            raise RuntimeError("tag_selector down")

    components = build_components(tags_tool=BoomTagsTool())
    resp = asyncio.run(ask_pipeline(build_request(), components))
    assert resp.messages[-1].content == "回答本文"
    assert components["search_tool"].calls[0]["tags"] == []


# --- /ask-agentic --------------------------------------------------------
def test_ask_agentic_stops_after_one_iteration_when_sufficient():
    """DoD 5: 初回検索で十分なら周回数1で generate へ抜ける。"""
    components = build_components()
    resp = asyncio.run(ask_agentic(build_request(), components))

    assert len(components["search_tool"].calls) == 1
    assert len(components["assessor"].calls) == 1
    assert resp.messages[-1].content == "回答本文"
    assert resp.messages[0].content.startswith("参考情報:\nQ: T1\nA: C1")


def test_ask_agentic_reformulates_query_and_searches_again():
    """DoD 6: 不十分なら next_query で search_knowledge が再度呼ばれる。"""
    search_tool = FakeSearchTool([
        [],
        [{"id": 2, "title": "T2", "content": "C2"}],
    ])
    components = build_components(
        search_tool=search_tool,
        assessor=FakeAssessor([insufficient("積算 手順 別の言い方"), SUFFICIENT]),
    )
    resp = asyncio.run(ask_agentic(build_request(), components))

    assert [c["query"] for c in search_tool.calls] == [
        "積算の操作方法を教えてください",
        "積算 手順 別の言い方",
    ]
    # 全周回の結果を統合した context で回答生成する（F-6.1.4）。
    assert "Q: T2\nA: C2" in resp.messages[0].content
    assert resp.messages[-1].content == "回答本文"


def test_ask_agentic_respects_max_iterations():
    """DoD 7: 上限に達したらそれ以上 search_knowledge を呼ばない。"""
    search_tool = FakeSearchTool([[{"id": 1, "title": "T1", "content": "C1"}]])
    components = build_components(
        search_tool=search_tool,
        assessor=FakeAssessor([insufficient("q2"), insufficient("q3")]),
    )
    asyncio.run(ask_agentic(build_request(), components))
    assert len(search_tool.calls) == 2  # AGENTIC_MAX_ITERATIONS の既定 2


def test_ask_agentic_max_iterations_is_configurable():
    search_tool = FakeSearchTool([[{"id": 1, "title": "T1", "content": "C1"}]])
    components = build_components(
        settings=FakeSettings(agentic_max_iterations=1),
        search_tool=search_tool,
        assessor=FakeAssessor([insufficient("q2")]),
    )
    asyncio.run(ask_agentic(build_request(), components))
    assert len(search_tool.calls) == 1


def test_ask_agentic_clarifies_when_nothing_found():
    """DoD 8: 上限まで探しても0件なら定型の謝罪文ではなく逆質問を返す。"""
    components = build_components(
        search_tool=FakeSearchTool([[]]),
        assessor=FakeAssessor([insufficient("q2"), insufficient("q3")]),
    )
    resp = asyncio.run(ask_agentic(build_request(), components))

    assert resp.messages[-1].content == "どの画面で発生しましたか？"
    assert resp.messages[-1].evaluation == 0
    assert resp.messages[-1].model == "fake-model"
    assert resp.messages[-1].input == "CLARIFY_PROMPT"
    # 逆質問時の user メッセージの context 部分は空（F-6.5.4）。
    assert resp.messages[0].content == "参考情報:\n\n\n質問:\n積算の操作方法を教えてください"
    # 不足観点と試したクエリが逆質問生成へ渡る（F-6.5.2）。
    _, _, tried, missing = components["clarifier"].calls[0]
    assert tried == ["積算の操作方法を教えてください", "q2"]
    assert missing == "手順の詳細"
    # 回答生成は呼ばれない（推測で回答しない, F-6.5.1）。
    assert components["generator"].calls == []


def test_ask_agentic_degrades_when_assessment_fails():
    """DoD 9: 十分性評価が失敗しても 500 にならず、1回検索＋回答生成で応答する。"""
    search_tool = FakeSearchTool([[{"id": 1, "title": "T1", "content": "C1"}]])
    components = build_components(
        search_tool=search_tool,
        assessor=FailingAssessor(),
    )
    resp = asyncio.run(ask_agentic(build_request(), components))

    assert len(search_tool.calls) == 1
    assert resp.messages[-1].content == "回答本文"


def test_ask_agentic_continues_when_search_fails():
    """F-6.3.9: search_knowledge の例外はその周回0件として扱い、ループを継続する。"""

    class BoomSearchTool:
        def __init__(self):
            self.calls = []

        async def ainvoke(self, args):
            self.calls.append(args)
            raise RuntimeError("knowledge_mcp down")

    search_tool = BoomSearchTool()
    components = build_components(
        search_tool=search_tool,
        assessor=FakeAssessor([insufficient("q2"), insufficient("q3")]),
    )
    resp = asyncio.run(ask_agentic(build_request(), components))

    assert len(search_tool.calls) == 2
    # 全周回0件 → 逆質問へ進む。
    assert resp.messages[-1].content == "どの画面で発生しましたか？"


def test_ask_agentic_uses_same_contract_as_ask_pipeline():
    """F-6.1.1: 応答スキーマ・組み立て形式が /ask-pipeline と同一であること。"""
    pipeline_resp = asyncio.run(ask_pipeline(build_request(), build_components()))
    agentic_resp = asyncio.run(ask_agentic(build_request(), build_components()))

    assert pipeline_resp.model_dump().keys() == agentic_resp.model_dump().keys()
    # ask_mode だけは方式を記録するため異なる（ADR-0099 §1）。それ以外は同一。
    def without_mode(resp):
        return [{k: v for k, v in m.model_dump().items() if k != "ask_mode"} for m in resp.messages]

    assert without_mode(pipeline_resp) == without_mode(agentic_resp)
    assert pipeline_resp.messages[-1].ask_mode == "pipeline"
    assert agentic_resp.messages[-1].ask_mode == "agentic"


def test_clarify_fallback_constant_matches_generate_rule_3():
    """F-6.5.3: 逆質問生成の失敗時フォールバックは generate.py ルール3 と同一文言。"""
    from agent_invitro.generate import _SYSTEM_PROMPT

    assert FALLBACK_CLARIFICATION in _SYSTEM_PROMPT
