"""オンメモリ SessionStore の実装。"""
from __future__ import annotations

from src.models.stateful import ConversationState


class InMemorySessionStore:
    """プロセス内メモリに ConversationState を保持する SessionStore。

    プロセス再起動でデータは失われる。
    開発・テスト・単一プロセス運用向け。
    """

    def __init__(self) -> None:
        self._store: dict[str, ConversationState] = {}

    def get(self, session_id: str) -> ConversationState | None:
        """セッション ID に対応する ConversationState を返す。存在しない場合は None。"""
        return self._store.get(session_id)

    def save(self, session_id: str, state: ConversationState) -> None:
        """ConversationState をメモリに保存する。"""
        self._store[session_id] = state

    def delete(self, session_id: str) -> None:
        """セッションをメモリから削除する。存在しない場合は何もしない。"""
        self._store.pop(session_id, None)
