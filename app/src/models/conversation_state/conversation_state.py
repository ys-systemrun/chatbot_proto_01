from __future__ import annotations

from .message import Message
from .slot import Slot


class ConversationState:
    def __init__(self) -> None:
        self._messages: list[Message] = []
        self.search_context: list = []
        self._slots: dict[str, Slot] = {}

    @property
    def messages(self) -> list[Message]:
        """メッセージリストのコピーを返す。追加は append_message を使うこと。"""
        return list(self._messages)

    @property
    def slots(self) -> dict[str, Slot]:
        """スロット辞書のコピーを返す。更新は set_slot を使うこと。"""
        return dict(self._slots)

    def append_message(self, role: str, content: str) -> None:
        self._messages.append(Message(role, content))

    def set_slot(self, key: str, value: str) -> None:
        self._slots[key] = Slot(key, value)

    def get_slot(self, key: str) -> str | None:
        slot = self._slots.get(key)
        return slot.value if slot is not None else None

    def messages_as_dicts(self) -> list[dict[str, str]]:
        """LLM API に渡せる dict のリストに変換する。"""
        return [m.to_dict() for m in self._messages]

    def to_dict(self) -> dict:
        """SessionStore への保存に使える dict に直列化する。"""
        return {
            "messages": self.messages_as_dicts(),
            "slots": {k: v.value for k, v in self._slots.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationState":
        """to_dict() の出力から ConversationState を復元する。"""
        state = cls()
        for m in data.get("messages", []):
            state.append_message(m["role"], m["content"])
        for k, v in data.get("slots", {}).items():
            state.set_slot(k, v)
        return state
