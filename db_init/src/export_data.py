"""退避エクスポート（ADR-0103, EXPORT_MODE）。

db_init を EXPORT_MODE で起動したときに実行される読み取り専用の処理。destroy-all / export-data
（terraform/deploy）が、破棄の前にデプロイ環境の全データを運用者の PC へ退避するために使う。

処理（データベースごと）:
  1. 1 つの REPEATABLE READ READ ONLY トランザクションを開き、テーブル間で同一時点のスナップショットにする。
  2. 対象テーブル（import_data の KNOWLEDGE_TABLES / CONVERSATION_TABLES）にも yoyo の管理テーブルにも
     含まれないテーブルが public スキーマにあれば失敗させる（対象リストの更新漏れのまま破棄しない）。
  3. テーブルごとの行数と、スキーマ版（yoyo の適用済みマイグレーション ID）を取得する。
  4. ADR-0066 の退避 SQL と同じ形式（TRUNCATE + INSERT）で SQL を生成する。import-data の投入ダンプとして
     そのまま使え、psql -f で直接適用しても退避時点の状態に戻る。

生成した SQL とマニフェスト（バイト数・SHA-256・行数・スキーマ版）は S3 の <prefix>/<ts>/ に置く。
manifest_only=True のときは SQL を作らず、マニフェスト（行数・スキーマ版）だけを置く
（import-data が投入先のスキーマ版を照合するのに使う）。
"""

from __future__ import annotations

import hashlib
import json

import psycopg2
import psycopg2.extensions

import import_data

# yoyo-migrations が作る管理テーブル（対象外テーブルの検出から除く）。
YOYO_TABLES = ("_yoyo_migration", "_yoyo_log", "_yoyo_version", "yoyo_lock")

LABELS = ("knowledge", "conversation")
MANIFEST_FILE = "manifest.json"
MANIFEST_FORMAT = 1


def sql_file_name(label: str) -> str:
    return f"{label}.sql"


def unexpected_tables(existing: list[str], expected: list[str]) -> list[str]:
    """public スキーマのテーブルのうち、対象テーブルにも yoyo の管理テーブルにも無いものを返す。"""
    known = set(expected) | set(YOYO_TABLES)
    return sorted(t for t in existing if t not in known)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _public_tables(cur) -> list[str]:
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    return [r[0] for r in cur.fetchall()]


def _schema_version(cur, existing: list[str]) -> list[str]:
    if "_yoyo_migration" not in existing:
        return []
    cur.execute("SELECT migration_id FROM _yoyo_migration ORDER BY migration_id")
    return [r[0] for r in cur.fetchall()]


def _row_counts(cur, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        # テーブル名は import_data の固定リストのため、二重引用符での quote_ident で安全。
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        counts[table] = cur.fetchone()[0]
    return counts


def export_database(conn, label: str, *, manifest_only: bool = False) -> "tuple[str | None, dict]":
    """1 データベースを同一スナップショットで読み出し、(SQL または None, 情報 dict) を返す。

    情報 dict は {"tables": {テーブル: 行数}, "schema_version": [マイグレーション ID]}。
    """
    tables = import_data.tables_for(label)
    conn.set_session(
        isolation_level=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ,
        readonly=True,
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            existing = _public_tables(cur)
            extra = unexpected_tables(existing, tables)
            if extra:
                raise RuntimeError(
                    f"{label} データベースに、退避の対象外のテーブルがあります: {', '.join(extra)}。"
                    " db_init/src/import_data.py の KNOWLEDGE_TABLES / CONVERSATION_TABLES"
                    "（と web_backend/src/export/tables.py）に追加してください（ADR-0103）。"
                )
            missing = [t for t in tables if t not in existing]
            if missing:
                raise RuntimeError(
                    f"{label} データベースに、対象テーブルが存在しません: {', '.join(missing)}。"
                    " マイグレーションの適用状態を確認してください。"
                )
            info = {
                "tables": _row_counts(cur, tables),
                "schema_version": _schema_version(cur, existing),
            }
        body = None
        if not manifest_only:
            body = import_data.build_backup_sql(
                conn, label, tables, title=f"ADR-0103 export of {label!r} database"
            )
        return body, info
    finally:
        conn.rollback()  # 読み取り専用トランザクションを閉じる


def build_manifest(*, created_at: str, timestamp: str, manifest_only: bool, databases: dict) -> dict:
    return {
        "format": MANIFEST_FORMAT,
        "adr": "ADR-0103",
        "created_at": created_at,
        "timestamp": timestamp,
        "manifest_only": manifest_only,
        "databases": databases,
    }


def run_export(
    *,
    knowledge_url: str,
    conversation_url: str,
    bucket: str,
    timestamp: str,
    prefix: str = "export",
    manifest_only: bool = False,
    region: str | None = None,
) -> dict:
    """両データベースを退避し、SQL とマニフェストを s3://<bucket>/<prefix>/<timestamp>/ に置く。"""
    urls = {"knowledge": knowledge_url, "conversation": conversation_url}
    s3 = import_data._s3_client(region)
    base = f"{prefix}/{timestamp}"
    mode = "manifest only" if manifest_only else "full"
    print(f"{import_data._now()} ====== EXPORT MODE start ({mode}, bucket={bucket}, ts={timestamp}).")

    databases: dict[str, dict] = {}
    for label in LABELS:
        url = urls[label]
        if not url:
            raise RuntimeError(f"{label} の接続 URL が未設定です（退避には両データベースの接続が必要）。")
        conn = psycopg2.connect(url)
        try:
            body, info = export_database(conn, label, manifest_only=manifest_only)
        finally:
            conn.close()
        entry = dict(info)
        if body is not None:
            data = body.encode("utf-8")
            key = f"{base}/{sql_file_name(label)}"
            import_data.upload_backup(s3, bucket, key, body)
            entry.update({"file": sql_file_name(label), "bytes": len(data), "sha256": sha256_hex(data)})
            print(f"{import_data._now()} [{label}] saved s3://{bucket}/{key} ({len(data)} bytes).")
        for table, count in info["tables"].items():
            print(f"{import_data._now()} [{label}] {table}: {count} rows")
        print(f"{import_data._now()} [{label}] schema version: {', '.join(info['schema_version']) or '(none)'}")
        databases[label] = entry

    manifest = build_manifest(
        created_at=import_data._now().isoformat(),
        timestamp=timestamp,
        manifest_only=manifest_only,
        databases=databases,
    )
    s3.put_object(
        Bucket=bucket,
        Key=f"{base}/{MANIFEST_FILE}",
        Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )
    print(f"{import_data._now()} ====== EXPORT MODE completed (s3://{bucket}/{base}/{MANIFEST_FILE}).")
    return manifest
