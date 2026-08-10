"""InferenceEngine の単体テスト（実装指示書 9.1）。

モック LLMClient を用い、confidence_threshold 未満の除外・max_tags 件への絞り込み・
score 降順ソート・JSONパース失敗時のフォールバック（空リスト）を検証する。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tag_selector_mcp.application.inference_engine import InferenceEngine
from tag_selector_mcp.application.retrieval_engine import RetrievalResult
from tag_selector_mcp.models.tag import TagRecord


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None

    def complete(self, prompt):
        self.last_prompt = prompt
        return self.response


def _candidates():
    return [
        TagRecord(id=1, name="A"),
        TagRecord(id=2, name="B"),
        TagRecord(id=3, name="C"),
    ]


def _result():
    return RetrievalResult(confirmed=[], candidates=_candidates())


def test_infer_basic_sort_and_path():
    llm = FakeLLM(
        '{"selected": [{"tag_id": 1, "score": 0.3}, {"tag_id": 2, "score": 0.9}]}'
    )
    engine = InferenceEngine(llm)
    out = engine.infer("q", _result(), max_tags=3, confidence_threshold=0.0)
    assert [(s.id, s.name) for s in out] == [(2, "B"), (1, "A")]
    assert out[0].path == ["B"]


def test_infer_confidence_threshold_filter():
    llm = FakeLLM(
        '{"selected": [{"tag_id": 1, "score": 0.3}, {"tag_id": 2, "score": 0.9}]}'
    )
    engine = InferenceEngine(llm)
    out = engine.infer("q", _result(), max_tags=3, confidence_threshold=0.5)
    assert [s.id for s in out] == [2]


def test_infer_max_tags_limit():
    llm = FakeLLM(
        '{"selected": [{"tag_id": 1, "score": 0.5}, '
        '{"tag_id": 2, "score": 0.9}, {"tag_id": 3, "score": 0.7}]}'
    )
    engine = InferenceEngine(llm)
    out = engine.infer("q", _result(), max_tags=2, confidence_threshold=0.0)
    assert [s.id for s in out] == [2, 3]


def test_infer_unknown_tag_id_ignored():
    llm = FakeLLM('{"selected": [{"tag_id": 99, "score": 0.9}]}')
    engine = InferenceEngine(llm)
    out = engine.infer("q", _result(), max_tags=3, confidence_threshold=0.0)
    assert out == []


def test_infer_unparseable_response_returns_empty():
    llm = FakeLLM("これはJSONではありません")
    engine = InferenceEngine(llm)
    out = engine.infer("q", _result(), max_tags=3, confidence_threshold=0.0)
    assert out == []


def test_infer_json_with_surrounding_text():
    # コードフェンスや前置き付きでも先頭の { .. } を抽出して解釈できる
    llm = FakeLLM('```json\n{"selected": [{"tag_id": 3, "score": 0.8}]}\n```')
    engine = InferenceEngine(llm)
    out = engine.infer("q", _result(), max_tags=3, confidence_threshold=0.0)
    assert [s.id for s in out] == [3]


def test_infer_propagates_llm_error():
    class BoomLLM:
        def complete(self, prompt):
            raise ConnectionError("LM Studio unreachable")

    engine = InferenceEngine(BoomLLM())
    with pytest.raises(ConnectionError):
        engine.infer("q", _result(), max_tags=3, confidence_threshold=0.0)


def test_prompt_includes_confirmed():
    llm = FakeLLM('{"selected": []}')
    engine = InferenceEngine(llm)
    result = RetrievalResult(
        confirmed=[TagRecord(id=1, name="A", aliases=["a"])],
        candidates=_candidates(),
    )
    engine.infer("q", result, max_tags=3, confidence_threshold=0.0)
    assert "id=1(A)" in llm.last_prompt
