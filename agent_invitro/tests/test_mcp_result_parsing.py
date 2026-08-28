"""MCPツール戻り値パースの頑健化テスト（ADR-0063 / 要件定義書 202608271500）。

langchain-mcp-adapters はバージョンにより戻り値が dict / JSON文字列 / bytes /
(content, artifact)タプル / テキストブロックのlist のいずれにもなり得る。旧実装は
テキストブロックの list を握りつぶし、select_tags の selected が常に空になっていた
（会話タグが常に0件 → タグなし検索）。本テストは全形式で selected / results を
取り出せることを保証する。
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_invitro.tags import _extract_selected_tags, _mcp_result_to_dicts


# 代表的なペイロード（tag_selector_mcp / knowledge_mcp が structuredContent で返す形）
_SELECTED = [{"id": 1, "name": "税務", "score": 0.9, "path": ["税務"]}]
_RESULTS = [{"id": "qa1", "title": "Q1", "content": "A1", "score": 0.8}]


def _text_block(payload: dict) -> dict:
    """MCP のテキストコンテンツブロック相当（{"type":"text","text":"<json>"}）。"""
    return {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}


def _lazy_extract_results():
    """server.py（FastAPI等の重い依存を引く）を遅延 import して _extract_results を返す。"""
    from agent_invitro.main.api.server import _extract_results

    return _extract_results


# --- select_tags: _extract_selected_tags -----------------------------------

def test_selected_from_dict():
    assert _extract_selected_tags({"selected": _SELECTED}) == _SELECTED


def test_selected_from_json_string():
    raw = json.dumps({"selected": _SELECTED}, ensure_ascii=False)
    assert _extract_selected_tags(raw) == _SELECTED


def test_selected_from_bytes():
    raw = json.dumps({"selected": _SELECTED}).encode("utf-8")
    assert _extract_selected_tags(raw) == _SELECTED


def test_selected_from_tuple_content_artifact():
    # response_format=content_and_artifact 相当（content にJSON文字列, artifact は別物）
    raw = (json.dumps({"selected": _SELECTED}), ["some-artifact"])
    assert _extract_selected_tags(raw) == _SELECTED


def test_selected_from_text_block_list():
    # ADR-0063 の本命ケース: テキストブロックの list を旧実装は握りつぶしていた
    raw = [_text_block({"selected": _SELECTED})]
    assert _extract_selected_tags(raw) == _SELECTED


def test_selected_empty_on_garbage():
    assert _extract_selected_tags("not json") == []
    assert _extract_selected_tags(None) == []
    assert _extract_selected_tags([{"type": "text", "text": "not json"}]) == []


def test_selected_empty_payload_is_empty_list():
    # selected が空配列（タグ該当なし）の正常系は [] を返す
    assert _extract_selected_tags({"selected": []}) == []


# --- 共通正規化 _mcp_result_to_dicts ---------------------------------------

def test_normalize_text_block_list_to_payload_dict():
    raw = [_text_block({"results": _RESULTS})]
    dicts = _mcp_result_to_dicts(raw)
    assert dicts == [{"results": _RESULTS}]


def test_normalize_bare_result_dict_list():
    # ラップ dict なしで結果 dict が並ぶ list はそのまま dict のリストになる
    dicts = _mcp_result_to_dicts(list(_RESULTS))
    assert dicts == _RESULTS


# --- search_knowledge: _extract_results ------------------------------------

def test_results_from_dict():
    assert _lazy_extract_results()({"results": _RESULTS}) == _RESULTS


def test_results_from_json_string():
    raw = json.dumps({"results": _RESULTS}, ensure_ascii=False)
    assert _lazy_extract_results()(raw) == _RESULTS


def test_results_from_text_block_list():
    raw = [_text_block({"results": _RESULTS})]
    assert _lazy_extract_results()(raw) == _RESULTS


def test_results_from_tuple_content_artifact():
    raw = (json.dumps({"results": _RESULTS}), None)
    assert _lazy_extract_results()(raw) == _RESULTS


def test_results_fallback_bare_result_list():
    # 「results」キーを持つ dict が無くても、id/title/content を持つ dict の list は結果とみなす
    assert _lazy_extract_results()(list(_RESULTS)) == _RESULTS


def test_results_empty_on_garbage():
    ex = _lazy_extract_results()
    assert ex("not json") == []
    assert ex(None) == []
    assert ex([{"type": "text", "text": "not json"}]) == []
