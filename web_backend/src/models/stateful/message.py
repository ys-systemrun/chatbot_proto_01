from __future__ import annotations

from typing import Literal

_VALID_ROLES = ("user", "assistant", "system")


class Message:
    def __init__(self, role: Literal["user", "assistant", "system"], content: str) -> None:
        self.role = role
        self.content = content

    @property
    def role(self) -> Literal["user", "assistant", "system"]:
        return self._role

    @role.setter
    def role(self, value: str) -> None:
        if value not in _VALID_ROLES:
            raise ValueError(f"role must be one of {_VALID_ROLES}, got {value!r}")
        self._role = value  # type: ignore[assignment]

    @property
    def content(self) -> str:
        return self._content

    @content.setter
    def content(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"content must be str, got {type(value).__name__}")
        self._content = value

    def to_dict(self) -> dict[str, str]:
        return {"role": self._role, "content": self._content}

    @classmethod
    def user(cls, content: str) -> Message:
        return cls("user", content)

    @classmethod
    def assistant(cls, content: str) -> Message:
        return cls("assistant", content)

    def __repr__(self) -> str:
        return f"Message(role={self._role!r}, content={self._content!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
        return self._role == other._role and self._content == other._content
