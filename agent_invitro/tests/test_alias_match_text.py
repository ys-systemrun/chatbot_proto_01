"""alias_match_text 構築ロジックのテスト（ADR-0086 決定4）。

「今回の発話＋未要約履歴のうち user 発話の質問文」を結合し、assistant 発話と要約済み
履歴を除外すること、user content の固定テンプレートから "質問:\n" 以降のみを抽出する
ことを検証する。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_invitro.tags import build_alias_match_text


@dataclass
class Msg:
    order: int
    role: str
    content: str


def _user_content(context: str, text: str) -> str:
    """server.py が user メッセージに使う固定テンプレートと同一形式。"""
    return f"参考情報:\n{context}\n\n質問:\n{text}"


def test_includes_req_text_and_user_questions():
    messages = [
        Msg(order=1, role="user", content=_user_content("記事X", "前の質問です")),
        Msg(order=2, role="assistant", content="前の回答です"),
    ]
    out = build_alias_match_text("今回の発話", messages, summarized_upto=0)
    assert "今回の発話" in out
    assert "前の質問です" in out
    # 参考情報（過去記事）と assistant 発話は含めない
    assert "記事X" not in out
    assert "前の回答です" not in out


def test_excludes_summarized_history():
    messages = [
        Msg(order=1, role="user", content=_user_content("記事X", "古い質問")),
        Msg(order=2, role="assistant", content="古い回答"),
        Msg(order=3, role="user", content=_user_content("記事Y", "新しい質問")),
    ]
    out = build_alias_match_text("今回", messages, summarized_upto=2)
    assert "新しい質問" in out
    assert "古い質問" not in out


def test_fallback_to_full_content_without_marker():
    # "質問:\n" マーカーが無い content は全文をフォールバックとして使う
    messages = [Msg(order=1, role="user", content="マーカー無しの生テキスト")]
    out = build_alias_match_text("今回", messages, summarized_upto=0)
    assert "マーカー無しの生テキスト" in out


def test_only_req_text_when_no_history():
    out = build_alias_match_text("単発の質問", [], summarized_upto=0)
    assert out == "単発の質問"


def test_uses_last_marker_when_context_contains_marker():
    # 参考情報側にも "質問:\n" が含まれる場合、最後の出現位置以降（実際の質問）を採る
    context = "Q: 過去のQ\nA: 質問:\nダミー"
    messages = [Msg(order=1, role="user", content=_user_content(context, "本当の質問"))]
    out = build_alias_match_text("今回", messages, summarized_upto=0)
    assert "本当の質問" in out
    assert "ダミー" not in out
