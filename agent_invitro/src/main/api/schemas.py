"""agent_invitro HTTP API の契約（スキーマ）定義（ADR-0090 決定1 / F-6.7.1）。

`/ask-pipeline`・`/ask-agentic` の両エンドポイントで共有する（ADR-0089 決定2）。
web_backend/src/main/controllers/chat_controller.py の同名モデルと同一契約であり、
片方だけを変更してはならない（ADR-0043 / 要件定義書6章）。
"""

from __future__ import annotations

from pydantic import BaseModel


class Message(BaseModel):
    order: int
    role: str
    content: str
    input: str | None = None        # assistant: LLM に渡したプロンプト
    model: str | None = None        # assistant: 使用モデル名
    evaluation: int | None = None   # user: null / assistant: 0=未評価 1=good 2=bad
    # --- ADR-0099 §1・§4: 回答を生成した構成と評価理由（assistant のみ）---
    release_id: str | None = None   # assistant: 回答を生成したリリース（GET /release で内容を取得）
    ask_mode: str | None = None     # assistant: "pipeline" | "agentic"
    evaluation_comment: str | None = None  # assistant: 評価の理由（画面で任意入力）
    # assistant: 回答の参考情報にした検索結果（順位順）。各要素は source_type / id / title / score。
    # 逆質問のときは空。評価ランナーが出典の正しさを採点するのに使う（ADR-0099 §5）。
    sources: list[dict] | None = None


class Summary(BaseModel):
    content: str
    summarized_upto: int


class Request(BaseModel):
    conversation_id: str | None = None  # None の場合はサーバー側で新規発行
    text: str
    messages: list[Message]
    summary: Summary


class Response(BaseModel):
    conversation_id: str
    messages: list[Message]
    summary: Summary
