"""既存 chatbot_db への接続（既存 app/src/db.py・Knowledge MCP のDB接続部分に準拠）。

Knowledge MCP の db/connection.py と同一方針で、呼び出しの都度 psycopg2 コネクションを
生成するファクトリを提供する。TagMetadataRepository はこの Database を DI で受け取り、
起動時ロード・リロード時にのみ read クエリを発行する（都度接続なので接続失効に強い）。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class Database:
    """DB接続ファクトリ。リポジトリにDIで渡す。"""

    def __init__(self, url: str):
        self.url = url

    def connect(self):
        """新規のpsycopg2コネクションを返す。

        psycopg2 は実行時にのみ必要なため、モジュール読み込み時ではなくここで import する
        （DB非依存の単体テストが psycopg2 未導入環境でも実行できるようにするため）。
        """
        import psycopg2

        return psycopg2.connect(self.url)

    @contextmanager
    def cursor(self) -> Iterator["psycopg2.extensions.cursor"]:
        """1回のDB操作ごとにコネクションを開き、正常終了でcommit・例外でrollbackする。

        使い方:
            with db.cursor() as cur:
                cur.execute(...)
        """
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
