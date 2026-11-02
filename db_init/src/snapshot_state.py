"""スナップショットの取り込み・書き出しの記録（ADR-0109 §6）。

データベースごとに 1 行だけの管理テーブル snapshot_state に、最後に取り込んだ・書き出したスナップショットの
ハッシュを記録する。取り込みの前に「投入先の今の中身が、記録した版のままか」を照合し、管理画面での編集を
黙って上書きしないようにするため。

このテーブルは yoyo のマイグレーションでは作らない（スキーマ版を変えると、それまでのスナップショットが
取り込めなくなるため）。必要になったときに CREATE TABLE IF NOT EXISTS で作り、書き出し・取り込みの対象外とする
（export_data.META_TABLES）。
"""

from __future__ import annotations

TABLE = "snapshot_state"


def ensure(cur) -> None:
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            snapshot_sha256 TEXT NOT NULL,
            kind TEXT NOT NULL,
            source TEXT,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def get(cur) -> "str | None":
    """記録されたハッシュ。テーブルが無い・行が無いなら None。"""
    cur.execute("SELECT to_regclass(%s)", (TABLE,))
    if cur.fetchone()[0] is None:
        return None
    cur.execute(f"SELECT snapshot_sha256 FROM {TABLE} WHERE id = 1")
    row = cur.fetchone()
    return row[0] if row else None


def write(cur, snapshot_sha256: str, *, kind: str, source: str) -> None:
    """開いているトランザクションの中で記録する（取り込みはデータの投入と同じトランザクションで記録する）。"""
    ensure(cur)
    cur.execute(
        f"""
        INSERT INTO {TABLE} (id, snapshot_sha256, kind, source, recorded_at) VALUES (1, %s, %s, %s, now())
        ON CONFLICT (id) DO UPDATE
        SET snapshot_sha256 = EXCLUDED.snapshot_sha256, kind = EXCLUDED.kind,
            source = EXCLUDED.source, recorded_at = EXCLUDED.recorded_at
        """,
        (snapshot_sha256, kind, source),
    )


def record(conn, snapshot_sha256: str, *, kind: str, source: str) -> None:
    """別のトランザクションで記録してコミットする（書き出しの後に使う）。"""
    with conn.cursor() as cur:
        write(cur, snapshot_sha256, kind=kind, source=source)
    conn.commit()
