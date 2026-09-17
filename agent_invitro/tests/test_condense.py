"""言い換え質問（condensed_query）生成ロジックのテスト（ADR-0085）。

Bedrock を呼ばずに検証するため、_invoke をスタブに差し替える。
- 会話文脈（要約・未要約履歴）が無い最初のターンは req.text をそのまま返す。
- LLM 呼び出しが例外を送出した場合は req.text へフォールバックする。
- LLM が空文字を返した場合も req.text へフォールバックする。
- system ロールのメッセージは言い換え入力から除外する。
- _build_user_content は要約・履歴セクションの有無を正しく組み立てる。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_invitro.condense import CondenseQueryLLMBedrock, _build_user_content


@dataclass
class Msg:
    role: str
    content: str


def _make(monkeypatched_invoke):
    """boto3 クライアント生成を避けつつ _invoke を差し替えたインスタンスを作る。"""
    obj = CondenseQueryLLMBedrock.__new__(CondenseQueryLLMBedrock)
    obj._model_id = "dummy"
    obj._max_tokens = 512
    obj._client = None
    obj._invoke = monkeypatched_invoke  # type: ignore[method-assign]
    return obj


def test_fallback_to_text_on_first_turn():
    # 要約も未要約履歴も無い最初のターンは LLM を呼ばずそのまま返す。
    called = []

    def _invoke(system, user_content):
        called.append(user_content)
        return "呼ばれてはいけない"

    condenser = _make(_invoke)
    out = condenser.condense("認証がうまくいきません", [], summary="")
    assert out == "認証がうまくいきません"
    assert called == []  # LLM は呼ばれない


def test_condenses_with_history():
    captured = {}

    def _invoke(system, user_content):
        captured["user_content"] = user_content
        return "ネットワーク認証でXXXという条件のときの対処方法は？"

    condenser = _make(_invoke)
    messages = [
        Msg(role="user", content="認証がうまくいきません"),
        Msg(role="assistant", content="ネットワーク認証ですか？"),
    ]
    out = condenser.condense("XXXという条件です", messages, summary="認証の相談")
    assert out == "ネットワーク認証でXXXという条件のときの対処方法は？"
    # 要約・履歴・今回の発話がプロンプトに含まれる。
    assert "認証の相談" in captured["user_content"]
    assert "認証がうまくいきません" in captured["user_content"]
    assert "XXXという条件です" in captured["user_content"]


def test_fallback_on_exception():
    def _invoke(system, user_content):
        raise RuntimeError("bedrock error")

    condenser = _make(_invoke)
    out = condenser.condense(
        "今回の発話", [Msg(role="user", content="前の発話")], summary="要約"
    )
    assert out == "今回の発話"


def test_fallback_on_empty_result():
    def _invoke(system, user_content):
        return "   "

    condenser = _make(_invoke)
    out = condenser.condense(
        "今回の発話", [Msg(role="user", content="前の発話")], summary="要約"
    )
    assert out == "今回の発話"


def test_excludes_system_messages():
    captured = {}

    def _invoke(system, user_content):
        captured["user_content"] = user_content
        return "言い換え結果"

    condenser = _make(_invoke)
    # system メッセージしか履歴が無く要約も無い場合は最初のターン扱い（フォールバック）。
    out = condenser.condense(
        "今回の発話", [Msg(role="system", content="システム指示")], summary=""
    )
    assert out == "今回の発話"


def test_build_user_content_omits_empty_sections():
    # 要約・履歴が無い場合は「今回の発話」セクションのみ。
    only = _build_user_content("発話のみ", [], "")
    assert "[会話の要約]" not in only
    assert "[直近の会話履歴]" not in only
    assert "[今回の発話]\n発話のみ" in only

    # 要約のみ有り。
    with_summary = _build_user_content("発話", [], "ここまでの要約")
    assert "[会話の要約]\nここまでの要約" in with_summary
    assert "[直近の会話履歴]" not in with_summary
