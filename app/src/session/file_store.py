"""ファイルシステムを永続化バックエンドとする SessionStore の実装。"""
from __future__ import annotations

import json
from pathlib import Path

from src.models.conversation_state import ConversationState


class FileSessionStore:
    """JSON ファイルに ConversationState を永続化する SessionStore。

    セッションごとに ``<store_dir>/<session_id>.json`` を作成する。
    単一サーバーでの永続化や、Redis を用意できない環境向け。
    """

    def __init__(self, store_dir: Path | str) -> None:
        """
        Args:
            store_dir: セッションファイルを格納するディレクトリのパス。
                       存在しない場合は自動作成する。
        """
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def get(self, session_id: str) -> ConversationState | None:
        """セッションファイルを読み込んで ConversationState を復元する。存在しない場合は None。"""
        p = self._path(session_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return ConversationState.from_dict(data)

    def save(self, session_id: str, state: ConversationState) -> None:
        """ConversationState を JSON ファイルに書き出す。"""
        self._path(session_id).write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete(self, session_id: str) -> None:
        """セッションファイルを削除する。存在しない場合は何もしない。"""
        self._path(session_id).unlink(missing_ok=True)
