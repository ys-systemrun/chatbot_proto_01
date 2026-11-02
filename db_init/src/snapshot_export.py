"""DB スナップショットの書き出し（ADR-0109 段階 1, EXPORT_MODE + EXPORT_FORMAT=csv）。

両データベースの対象テーブル（import_data の KNOWLEDGE_TABLES / CONVERSATION_TABLES）を、
1 つの REPEATABLE READ READ ONLY トランザクションの中でテーブルごとの CSV に書き出す。

- 書式は PostgreSQL の COPY ... CSV（HEADER, FORCE_QUOTE *）。NULL は引用符なしの空欄、空文字列は ""。
  真偽値・日時・数値も PostgreSQL の表現のまま（取り込みも COPY で行い、値をそのまま往復させる）。
- 行は主キーの順（主キーが無ければ全列の順）。差分が読めるようにするため。
- 列は DB の全列から、埋め込み（pgvector の vector 型の列）を除いたもの。
- DB の ID（通し番号）もそのまま書き出す（取り込みは全消去→全行投入のため, ADR-0109 §4）。

置き場所は S3（<prefix>/<ts>/<db>/<table>.csv と <prefix>/<ts>/manifest.json）か、ローカルのディレクトリ
（EXPORT_DIR。<dir>/<db>/<table>.csv と <dir>/manifest.json）。マニフェストには、テーブルごとの行数・列・
SHA-256 と、データベースごとのスナップショット全体のハッシュ・スキーマ版を記録する。
"""

from __future__ import annotations

import hashlib
import io
import json
import os

import psycopg2
import psycopg2.extensions
from psycopg2 import sql

import embedding_cache
import export_data
import import_data
import snapshot_state

MANIFEST_FORMAT = 2


def csv_file_name(table: str) -> str:
    return f"{table}.csv"


def snapshot_sha256(table_hashes: dict[str, str]) -> str:
    """データベース全体のハッシュ。テーブルの並び（対象リストの順）と各 CSV のハッシュから決める。"""
    text = "".join(f"{table} {digest}\n" for table, digest in table_hashes.items())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _snapshot_columns(cur, table: str) -> list[str]:
    """書き出す列（定義順）。pgvector の vector 型（埋め込み）は除く。"""
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND udt_name <> 'vector'
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def copy_query(table: str, columns: list[str], order_by: list[str]) -> sql.Composed:
    return sql.SQL(
        "COPY (SELECT {cols} FROM {table} ORDER BY {order}) TO STDOUT WITH (FORMAT csv, HEADER, FORCE_QUOTE *)"
    ).format(
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        table=sql.Identifier(table),
        order=sql.SQL(", ").join(sql.Identifier(c) for c in order_by),
    )


def _copy_table(cur, table: str, columns: list[str], order_by: list[str]) -> bytes:
    buf = io.BytesIO()
    cur.copy_expert(copy_query(table, columns, order_by), buf)
    return buf.getvalue()


def read_snapshot(cur, label: str) -> "tuple[dict[str, bytes], dict]":
    """開いているトランザクションの中で 1 データベースを CSV にし、({テーブル: CSV}, マニフェストの項目) を返す。

    書き出し（読み取り専用トランザクション）と、取り込み（書き込みトランザクションの中での照合）の両方で使う。
    """
    tables = import_data.tables_for(label)
    existing = export_data._public_tables(cur)
    extra = export_data.unexpected_tables(existing, tables)
    if extra:
        raise RuntimeError(
            f"{label} データベースに、書き出しの対象外のテーブルがあります: {', '.join(extra)}。"
            " db_init/src/import_data.py の KNOWLEDGE_TABLES / CONVERSATION_TABLES に追加してください。"
        )
    missing = [t for t in tables if t not in existing]
    if missing:
        raise RuntimeError(f"{label} データベースに、対象テーブルが存在しません: {', '.join(missing)}。")

    files: dict[str, bytes] = {}
    entries: dict[str, dict] = {}
    for table in tables:
        columns = _snapshot_columns(cur, table)
        order_by = import_data._pk_columns(cur, table) or columns
        data = _copy_table(cur, table, columns, order_by)
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
        files[table] = data
        entries[table] = {
            "file": csv_file_name(table),
            "rows": cur.fetchone()[0],
            "columns": columns,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    info = {
        "tables": entries,
        "schema_version": export_data._schema_version(cur, existing),
        "snapshot_sha256": snapshot_sha256({t: e["sha256"] for t, e in entries.items()}),
    }
    return files, info


def export_snapshot(conn, label: str) -> "tuple[dict[str, bytes], dict]":
    """1 データベースを同一時点（REPEATABLE READ READ ONLY）で CSV に書き出す。"""
    conn.set_session(
        isolation_level=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ,
        readonly=True,
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            return read_snapshot(cur, label)
    finally:
        conn.rollback()  # 読み取り専用トランザクションを閉じる
        conn.set_session(isolation_level=None, readonly=False, autocommit=False)


def build_manifest(*, created_at: str, timestamp: str, databases: dict) -> dict:
    return {
        "format": MANIFEST_FORMAT,
        "adr": "ADR-0109",
        "kind": "snapshot",
        "created_at": created_at,
        "timestamp": timestamp,
        "databases": databases,
    }


def split_manifest(manifest: dict) -> dict[str, dict]:
    """全体のマニフェストを、データベースごとのマニフェストに分ける（埋め込みキャッシュの項目は knowledge に付ける）。"""
    common = {k: v for k, v in manifest.items() if k not in ("databases", "embedding_cache")}
    result = {}
    for label, entry in manifest["databases"].items():
        own = dict(common, databases={label: entry})
        if label == "knowledge" and manifest.get("embedding_cache"):
            own["embedding_cache"] = manifest["embedding_cache"]
        result[label] = own
    return result


def _write_local(directory: str, label: str, files: dict[str, bytes]) -> None:
    target = os.path.join(directory, label)
    os.makedirs(target, exist_ok=True)
    for table, data in files.items():
        with open(os.path.join(target, csv_file_name(table)), "wb") as f:
            f.write(data)


def build_embedding_cache(knowledge_url: str, cache_root: "str | None", model_id: str, *, source: str) -> "tuple[dict[str, bytes], dict]":
    """既存のキャッシュに knowledge DB の埋め込みを足した新しいキャッシュを作る（ADR-0109 段階 3）。

    ({ファイル名: 中身}, マニフェストの項目) を返す。置き場所は <embedding_cache>/<モデル ID のディレクトリ名>/。
    """
    existing = embedding_cache.load(cache_root, model_id) if cache_root else None
    conn = psycopg2.connect(knowledge_url)
    try:
        with conn.cursor() as cur:
            from_db = embedding_cache.collect_from_db(cur)
        conn.rollback()
    finally:
        conn.close()
    merged, added = embedding_cache.merge(existing, from_db)
    data = embedding_cache.render(merged)
    meta = embedding_cache.render_meta(model_id, merged, source=source)
    files = {embedding_cache.EMBEDDINGS_FILE: data, embedding_cache.META_FILE: meta}
    entry = {
        "model_id": model_id,
        "dir": f"embedding_cache/{embedding_cache.dir_name(model_id)}",
        "entries": len(merged),
        "added": added,
        "files": {name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()} for name, body in files.items()},
    }
    return files, entry


def run_snapshot_export(
    *,
    knowledge_url: str,
    conversation_url: str,
    timestamp: str,
    bucket: str | None = None,
    prefix: str = "snapshot",
    directory: str | None = None,
    region: str | None = None,
    cache_root: str | None = None,
    model_id: str | None = None,
) -> dict:
    """両データベースを書き出す。directory があればローカルへ、無ければ s3://<bucket>/<prefix>/<ts>/ へ置く。

    model_id があれば、埋め込みキャッシュ（cache_root の既存分に knowledge DB の埋め込みを足したもの）も
    <置き場所>/embedding_cache/<モデル ID のディレクトリ名>/ に書き出す。
    """
    if not directory and not bucket:
        raise RuntimeError("書き出し先がありません（EXPORT_DIR か IMPORT_BUCKET を指定してください）。")
    urls = {"knowledge": knowledge_url, "conversation": conversation_url}
    s3 = None if directory else import_data._s3_client(region)
    base = f"{prefix}/{timestamp}"
    where = directory if directory else f"s3://{bucket}/{base}/"
    print(f"{import_data._now()} ====== SNAPSHOT EXPORT start (ADR-0109, to {where}, ts={timestamp}).")

    databases: dict[str, dict] = {}
    for label in export_data.LABELS:
        url = urls[label]
        if not url:
            raise RuntimeError(f"{label} の接続 URL が未設定です（書き出しには両データベースの接続が必要）。")
        conn = psycopg2.connect(url)
        try:
            files, info = export_snapshot(conn, label)
            # 書き出した版を記録する（次の取り込みで「最後の書き出しから変わっていないか」を照合するため）。
            snapshot_state.record(conn, info["snapshot_sha256"], kind="export", source=f"{where} ts={timestamp}")
        finally:
            conn.close()
        if directory:
            _write_local(directory, label, files)
        else:
            for table, data in files.items():
                s3.put_object(
                    Bucket=bucket,
                    Key=f"{base}/{label}/{csv_file_name(table)}",
                    Body=data,
                    ContentType="text/csv; charset=utf-8",
                )
        for table, entry in info["tables"].items():
            print(f"{import_data._now()} [{label}] {table}: {entry['rows']} rows ({entry['bytes']} bytes)")
        print(f"{import_data._now()} [{label}] snapshot sha256: {info['snapshot_sha256']}")
        databases[label] = info

    manifest = build_manifest(created_at=import_data._now().isoformat(), timestamp=timestamp, databases=databases)
    if model_id:
        files, entry = build_embedding_cache(knowledge_url, cache_root, model_id, source=f"{where} ts={timestamp}")
        for name, data in files.items():
            if directory:
                target = os.path.join(directory, entry["dir"])
                os.makedirs(target, exist_ok=True)
                with open(os.path.join(target, name), "wb") as f:
                    f.write(data)
            else:
                s3.put_object(Bucket=bucket, Key=f"{base}/{entry['dir']}/{name}", Body=data)
        print(
            f"{import_data._now()} [embedding cache] {model_id}: {entry['entries']} entries"
            f" ({entry['added']} added from the database)"
        )
        manifest["embedding_cache"] = entry
    body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    if directory:
        with open(os.path.join(directory, export_data.MANIFEST_FILE), "wb") as f:
            f.write(body)
        # データベースごとのフォルダにも、そのデータベースだけのマニフェストを置く（kb-export と同じ形。
        # そのまま IMPORT_DIR・シードの取り込み元に使える）。
        for label, own in split_manifest(manifest).items():
            with open(os.path.join(directory, label, export_data.MANIFEST_FILE), "w", encoding="utf-8", newline="\n") as f:
                json.dump(own, f, ensure_ascii=False, indent=2)
    else:
        s3.put_object(
            Bucket=bucket,
            Key=f"{base}/{export_data.MANIFEST_FILE}",
            Body=body,
            ContentType="application/json; charset=utf-8",
        )
    print(f"{import_data._now()} ====== SNAPSHOT EXPORT completed.")
    return manifest
