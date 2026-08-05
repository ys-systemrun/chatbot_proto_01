"""SessionStore のインターフェース定義。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.models.stateful import ConversationState


@runtime_checkable
class SessionStore(Protocol):
    """ConversationState をセッション ID に紐づけて管理するストアのインターフェース。

    各実装は get / save / delete の 3 メソッドを提供する。
    呼び出し側は get で取得した state を変更した後、必ず save を呼ぶこと。
    """

    def get(self, session_id: str) -> ConversationState | None:
        """セッション ID に対応する ConversationState を返す。存在しない場合は None。"""
        ...

    def save(self, session_id: str, state: ConversationState) -> None:
        """ConversationState をセッション ID に紐づけて保存する。既存エントリは上書き。"""
        ...

    def delete(self, session_id: str) -> None:
        """セッション ID に対応するデータを削除する。存在しない場合は何もしない。"""
        ...
