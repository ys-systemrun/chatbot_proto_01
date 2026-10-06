from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MessageRecord:
    order: int
    role: int            # 1=user, 2=assistant
    evaluation: int | None = None
    input: str | None = None
    model: str | None = None
    content: str | None = None
    # --- ADR-0099 §1・§4 ---
    release_id: str | None = None          # assistant: 回答を生成したリリース
    ask_mode: str | None = None            # assistant: "pipeline" | "agentic"
    evaluation_comment: str | None = None  # assistant: 評価の理由（任意）


@dataclass
class ReleaseData:
    """回答を生成した構成（ADR-0099 §1）。agent_invitro の GET /release と同じ要素。"""

    release_id: str
    git_commit: str | None = None
    git_dirty: bool | None = None
    prompt_hash: str | None = None
    chat_model_id: str | None = None
    embedding_model_id: str | None = None
    params: dict | None = None
    first_seen_at: str | None = None


@dataclass
class EvaluatedMessageData:
    id: str
    order: int
    role: int
    evaluation: int | None
    input: str | None
    model: str | None
    content: str | None
    created_at: str
    release_id: str | None = None
    ask_mode: str | None = None
    evaluation_comment: str | None = None
    evaluated_at: str | None = None
    release: ReleaseData | None = None


@dataclass
class EvaluatedConversationData:
    id: str
    created_at: str
    messages: list[EvaluatedMessageData] = field(default_factory=list)
