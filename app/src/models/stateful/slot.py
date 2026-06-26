from __future__ import annotations


class Slot:
    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value

    @property
    def key(self) -> str:
        return self._key

    @key.setter
    def key(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("key must be a non-empty string")
        self._key = value

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, v: str) -> None:
        if not isinstance(v, str):
            raise TypeError(f"value must be str, got {type(v).__name__}")
        self._value = v

    def __repr__(self) -> str:
        return f"Slot(key={self._key!r}, value={self._value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Slot):
            return NotImplemented
        return self._key == other._key and self._value == other._value
