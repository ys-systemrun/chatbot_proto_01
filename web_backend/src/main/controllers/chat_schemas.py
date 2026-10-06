"""チャット（stateless 会話）の API 契約。

`chat_controller`（ローカル直接処理）と `agent_controller`（agent_invitro への中継）の
両方が同一のスキーマを使うため、どちらにも属さない独立モジュールとして切り出したもの。
`agent_invitro/src/main/api/schemas.py` と同一契約であり、片方だけを変更してはならない
（ADR-0043 / ADR-0089 決定2 / 要件定義書6章）。
"""

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
