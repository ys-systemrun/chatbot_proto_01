"""既存 chatbot_db への接続（既存 app/src/db.py のDB接続部分に準拠）。

長時間常駐するMCPサーバでは1本のコネクションを保持し続けると接続が失効しやすい。
また ADR-0006 の「タグ情報をキャッシュしない（都度DB参照）」方針とも整合させるため、
本モジュールは呼び出しの都度 psycopg2 コネクションを生成するファクトリを提供する。
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

        psycopg2 は接続時のみ必要なため、遅延importする
        （Fake DB を使う単体テストがドライバ未導入環境でも動くようにする）。
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


def to_vector_str(vec) -> str:
    """embeddingベクトルを pgvector のリテラル文字列へ変換する（既存 db.py と同一）。"""
    return "[" + ",".join(map(str, vec)) + "]"
