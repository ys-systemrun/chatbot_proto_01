"""Redis を永続化バックエンドとする SessionStore の実装。"""
from __future__ import annotations

import json
from typing import Any

from src.models.conversation_state import ConversationState


class RedisSessionStore:
    """Redis に ConversationState を保存する SessionStore。

    TTL によるセッション自動失効をサポートする。
    複数ワーカー・複数コンテナのような分散環境向け。

    依存パッケージ: ``pip install redis``
    """

    def __init__(self, url: str, ttl_seconds: int = 1800) -> None:
        """
        Args:
            url: Redis の接続 URL。例: ``"redis://localhost:6379/0"``
            ttl_seconds: セッションの有効期間（秒）。デフォルトは 30 分。
                         save のたびに TTL がリセットされる。
        """
        try:
            import redis
        except ImportError as e:
            raise ImportError(
                "RedisSessionStore を使用するには redis パッケージが必要です: "
                "pip install redis"
            ) from e
        self._client: Any = redis.from_url(url)
        self._ttl = ttl_seconds

    def get(self, session_id: str) -> ConversationState | None:
        """Redis からセッションデータを取得して ConversationState を復元する。存在しない場合は None。"""
        raw = self._client.get(session_id)
        if raw is None:
            return None
        return ConversationState.from_dict(json.loads(raw))

    def save(self, session_id: str, state: ConversationState) -> None:
        """ConversationState を Redis に保存する。TTL をリセットする。"""
        self._client.setex(
            session_id,
            self._ttl,
            json.dumps(state.to_dict(), ensure_ascii=False),
        )

    def delete(self, session_id: str) -> None:
        """セッションキーを Redis から削除する。存在しない場合は何もしない。"""
        self._client.delete(session_id)
