"""エントリポイント（実装指示書 T11 / ADR-0007, ADR-0011）。

Tag Selector MCP サーバを Streamable HTTP で起動する。
起動時に TagMetadataRepository.load() を実行し、リロード間隔ごとに reload() を呼ぶ
デーモンスレッド（定期ポーリング）を開始してから MCP サーバを起動する。

MCPエンドポイントは既定で /mcp、ヘルスチェックは /health に公開される。

    python -m tag_selector_mcp.main
"""

from __future__ import annotations

import logging
import threading

from .mcp.server import build_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _start_polling(tag_repository, interval_sec: int, stop_event: threading.Event) -> threading.Thread:
    """interval_sec ごとに reload() を呼ぶデーモンスレッドを開始する（ADR-0011）。

    reload() が失敗しても（DB一時停止等）ログに記録して継続する。スレッド内では
    呼び出し元へ伝播できないため、ここで例外を握りつぶす（キャッシュは維持される）。
    """

    def loop() -> None:
        while not stop_event.wait(interval_sec):
            try:
                tag_repository.reload()
            except Exception:
                logger.exception("periodic taxonomy reload failed; keeping existing cache")

    thread = threading.Thread(target=loop, name="taxonomy-poller", daemon=True)
    thread.start()
    return thread


def main() -> None:
    components = build_server()

    # 起動時ロード。ここで失敗した場合は例外を伝播させ、起動を中断する（5.2節・起動処理）。
    components.tag_repository.load()

    # 定期ポーリング（ADR-0011）。daemon スレッドなのでサーバ終了時に自動的に停止する。
    stop_event = threading.Event()
    _start_polling(
        components.tag_repository,
        components.reload_interval_sec,
        stop_event,
    )

    try:
        components.mcp.run(transport="streamable-http")
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
