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
