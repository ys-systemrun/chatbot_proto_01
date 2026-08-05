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


@dataclass
class EvaluatedConversationData:
    id: str
    created_at: str
    messages: list[EvaluatedMessageData] = field(default_factory=list)
