"""DB スナップショットの取り込み（ADR-0109 段階 2, IMPORT_MODE + IMPORT_FORMAT=csv）。

snapshot_export が書き出した CSV（テーブルごと, PostgreSQL の COPY 形式）とマニフェストから、データベースを
全消去→全行投入で戻す。取り込み元は S3（<prefix>/<db>/manifest.json と CSV）かローカルのディレクトリ
（<dir>/<db>/manifest.json と CSV。シードでイメージ同梱の /data/knowledge を読む用途）。

データベースごとの処理:
  1. CSV の SHA-256 とデータベース全体のハッシュがマニフェストと一致することを確かめる（全消去の前）。
  2. スキーマ版（yoyo の適用済み ID）がマニフェストと同じことを確かめる。
  3. 投入先にデータがあれば、今の中身のハッシュが snapshot_state の記録（最後に取り込んだ・書き出した版）と
     同じことを確かめる。管理画面での編集を黙って上書きしないため（ADR-0109 §6）。
  4. S3 から取り込むときは、消す前のデータを退避 SQL にして S3 の rollback/ に置く（ADR-0066 と同じ）。
  5. 1 トランザクションで: 全消去 → COPY で全行投入 → シーケンスの調整 → 投入結果を書き出し直して
     マニフェストのハッシュと一致することを確認 → 埋め込みをキャッシュから補う → snapshot_state に記録。
     途中で失敗したら全体が元に戻る。

2・3 は force=True のときだけ飛ばせる（警告を出す）。
埋め込みはスナップショットに含めないため、キャッシュ（モデル ID × 埋め込み元テキストの SHA-256）から補う。
キャッシュに無い行は NULL のまま残り、件数を表示する（計算して補うのは段階 3）。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_batch

import export_data
import import_data
import snapshot_export
import snapshot_state
import troubleshooting_import

MANIFEST_FILE = export_data.MANIFEST_FILE


# ---------------------------------------------------------------------------
# 取り込み元（ローカル / S3）
# ---------------------------------------------------------------------------
def _manifest_entry(manifest: dict, label: str) -> dict:
    entry = (manifest.get("databases") or {}).get(label)
    if not entry:
        raise RuntimeError(f"マニフェストに {label} がありません。")
    return entry


def load_local(directory: str, label: str) -> "tuple[dict, dict[str, bytes]]":
    """<directory>/<label>/ のマニフェストと CSV を読む。"""
    base = os.path.join(directory, label)
    with open(os.path.join(base, MANIFEST_FILE), encoding="utf-8") as f:
        entry = _manifest_entry(json.load(f), label)
    files = {}
    for table, info in entry["tables"].items():
        with open(os.path.join(base, info["file"]), "rb") as f:
            files[table] = f.read()
    return entry, files


def load_s3(s3, bucket: str, prefix: str, label: str) -> "tuple[dict, dict[str, bytes]]":
    """s3://<bucket>/<prefix>/<label>/ のマニフェストと CSV を読む。"""
    base = f"{prefix}/{label}"
    manifest = json.loads(s3.get_object(Bucket=bucket, Key=f"{base}/{MANIFEST_FILE}")["Body"].read())
    entry = _manifest_entry(manifest, label)
    files = {
        table: s3.get_object(Bucket=bucket, Key=f"{base}/{info['file']}")["Body"].read()
        for table, info in entry["tables"].items()
    }
    return entry, files


# ---------------------------------------------------------------------------
# 照合（純関数）
# ---------------------------------------------------------------------------
def verify_files(label: str, entry: dict, files: dict[str, bytes]) -> None:
    """対象テーブルがそろい、各 CSV と全体のハッシュがマニフェストと一致することを確かめる。"""
    tables = import_data.tables_for(label)
    if list(entry["tables"]) != tables:
        raise RuntimeError(
            f"{label} のスナップショットのテーブル構成が対象テーブルと違います: {list(entry['tables'])}（期待: {tables}）"
        )
    hashes = {}
    for table in tables:
        hashes[table] = hashlib.sha256(files[table]).hexdigest()
        if hashes[table] != entry["tables"][table]["sha256"]:
            raise RuntimeError(f"{label}.{table} の CSV の SHA-256 がマニフェストと一致しません。")
    if snapshot_export.snapshot_sha256(hashes) != entry["snapshot_sha256"]:
        raise RuntimeError(f"{label} のスナップショット全体のハッシュがマニフェストと一致しません。")


def csv_header(data: bytes) -> list[str]:
    first = data.split(b"\n", 1)[0].decode("utf-8")
    return next(csv.reader([first]))


def schema_problem(expected: list[str], actual: list[str]) -> "str | None":
    if expected == actual:
        return None
    return f"スキーマ版が違います（スナップショット: {expected[-1:] or '(なし)'} / 投入先: {actual[-1:] or '(なし)'}）"


def drift_problem(has_data: bool, current: "str | None", recorded: "str | None") -> "str | None":
    """投入先が、記録した版から変わっていれば理由を返す（空なら問題なし）。"""
    if not has_data:
        return None
    if recorded is None:
        return "投入先にデータがあり、取り込み・書き出しの記録がありません（どの版か分からないため上書きしません）"
    if current != recorded:
        return "投入先の中身が、最後に取り込んだ・書き出した版から変わっています（管理画面での編集など）"
    return None


# ---------------------------------------------------------------------------
# 埋め込みキャッシュ（ADR-0109 §5）
# ---------------------------------------------------------------------------
def cache_dir_name(model_id: str) -> str:
    """モデル ID をディレクトリ名にする（Windows で使えない ':' などを '_' に）。"""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in model_id)


def load_embedding_cache(cache_root: str, model_id: str) -> "dict[str, str] | None":
    """{埋め込み元テキストの SHA-256: pgvector 形式のベクトル}。キャッシュが無ければ None。"""
    path = os.path.join(cache_root, cache_dir_name(model_id), "embeddings.csv")
    if not os.path.exists(path):
        return None
    csv.field_size_limit(1 << 30)
    with open(path, encoding="utf-8", newline="") as f:
        return {row["text_sha256"]: row["embedding"] for row in csv.DictReader(f)}


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vector_dim(cur, table: str) -> "int | None":
    cur.execute(
        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = %s::regclass AND attname = 'embedding'",
        (table,),
    )
    row = cur.fetchone()
    if not row or not row[0].startswith("vector("):
        return None
    return int(row[0][len("vector("):-1])


def fill_embeddings(cur, cache: dict[str, str]) -> dict:
    """knowledge の embedding が NULL の行を、キャッシュから補う。{テーブル: (補った件数, 残った件数)} を返す。"""
    stats = {}
    any_vec = next(iter(cache.values()), None)
    cache_dim = len(any_vec.strip("[]").split(",")) if any_vec else None

    # 言い換え質問文: 埋め込み元は text。
    if _vector_dim(cur, "hiroba_question_altered") == cache_dim:
        cur.execute("SELECT id, text FROM hiroba_question_altered WHERE embedding IS NULL")
        pairs = [(cache[text_key(t)], i) for i, t in cur.fetchall() if t is not None and text_key(t) in cache]
        execute_batch(cur, "UPDATE hiroba_question_altered SET embedding = %s::vector WHERE id = %s", pairs)
        cur.execute("SELECT COUNT(*) FROM hiroba_question_altered WHERE embedding IS NULL")
        stats["hiroba_question_altered"] = (len(pairs), cur.fetchone()[0])

    # トラブルシューティング記事: 埋め込み元はシードと同じ build_embedding_text。
    if _vector_dim(cur, "troubleshooting_article") == cache_dim:
        cur.execute(
            "SELECT id, title, subtitle, symptom, cause, guidance FROM troubleshooting_article WHERE embedding IS NULL"
        )
        pairs = []
        for aid, title, subtitle, symptom, cause, guidance in cur.fetchall():
            article = troubleshooting_import.TroubleshootingArticle(
                source_key="", title=title, body_html="", guidance=guidance or "",
                subtitle=subtitle, symptom=symptom, cause=cause,
            )
            key = text_key(troubleshooting_import.build_embedding_text(article))
            if key in cache:
                pairs.append((cache[key], aid))
        execute_batch(cur, "UPDATE troubleshooting_article SET embedding = %s::vector WHERE id = %s", pairs)
        cur.execute("SELECT COUNT(*) FROM troubleshooting_article WHERE embedding IS NULL")
        stats["troubleshooting_article"] = (len(pairs), cur.fetchone()[0])
    return stats


def backfill_missing_embeddings(url: str, embed_fn, *, batch_size: int = 100) -> dict:
    """knowledge の embedding が NULL の行を、埋め込み API で計算して埋める（ADR-0109 段階 3）。

    キャッシュに無かった行（別の埋め込みモデルのローカル環境・本番で欠けていた記事など）が対象。
    取り込みのトランザクションとは分け、batch_size 件ごとにコミットする（途中で止まっても、次の実行で
    残りだけを続きから埋める）。埋め込みはスナップショットのハッシュに含めないため、取り込みの記録は変わらない。
    """
    stats = {}
    targets = {
        "hiroba_question_altered": "SELECT id, text FROM hiroba_question_altered WHERE embedding IS NULL ORDER BY id",
        "troubleshooting_article": (
            "SELECT id, title, subtitle, symptom, cause, guidance FROM troubleshooting_article "
            "WHERE embedding IS NULL ORDER BY id"
        ),
    }
    conn = psycopg2.connect(url)
    try:
        for table, query in targets.items():
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
            done = 0
            for start in range(0, len(rows), batch_size):
                with conn.cursor() as cur:
                    for row in rows[start:start + batch_size]:
                        if table == "hiroba_question_altered":
                            text = row[1] or ""
                        else:
                            article = troubleshooting_import.TroubleshootingArticle(
                                source_key="", title=row[1], body_html="", guidance=row[5] or "",
                                subtitle=row[2], symptom=row[3], cause=row[4],
                            )
                            text = troubleshooting_import.build_embedding_text(article)
                        if not text:
                            continue
                        vector = "[" + ",".join(str(v) for v in embed_fn(text)) + "]"
                        cur.execute(
                            sql.SQL("UPDATE {} SET embedding = %s::vector WHERE id = %s").format(sql.Identifier(table)),
                            (vector, row[0]),
                        )
                        done += 1
                conn.commit()
            stats[table] = done
            print(f"{import_data._now()} [knowledge] {table}: embeddings computed {done} / {len(rows)}")
    finally:
        conn.close()
    return stats


# ---------------------------------------------------------------------------
# 取り込み
# ---------------------------------------------------------------------------
def _has_data(cur, tables: list[str]) -> bool:
    for table in tables:
        cur.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(sql.Identifier(table)))
        if cur.fetchone()[0]:
            return True
    return False


def check_target(conn, label: str, entry: dict, *, force: bool) -> bool:
    """スキーマ版と、投入先が記録した版のままかを照合する。投入先にデータがあれば True を返す。"""
    tables = import_data.tables_for(label)
    with conn.cursor() as cur:
        existing = export_data._public_tables(cur)
        problems = [schema_problem(entry["schema_version"], export_data._schema_version(cur, existing))]
        has_data = _has_data(cur, tables)
        current = snapshot_export.read_snapshot(cur, label)[1]["snapshot_sha256"] if has_data else None
        problems.append(drift_problem(has_data, current, snapshot_state.get(cur)))
    conn.rollback()
    problems = [p for p in problems if p]
    for p in problems:
        if not force:
            raise RuntimeError(f"[{label}] {p}。取り込みを中止しました（承知のうえで続けるなら IMPORT_FORCE=true）。")
        print(f"{import_data._now()} [{label}] WARNING: {p}（IMPORT_FORCE=true のため続行）")
    return has_data


def import_database(conn, label: str, entry: dict, files: dict[str, bytes], *, cache, source: str) -> dict:
    """1 トランザクションで全消去→COPY 投入→シーケンス調整→ハッシュ照合→埋め込み補完→記録を行う。"""
    tables = import_data.tables_for(label)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(import_data._truncate_statement(tables))
            for table in tables:
                data = files[table]
                columns = entry["tables"][table]["columns"]
                if csv_header(data) != columns:
                    raise RuntimeError(f"{label}.{table} の CSV の列名がマニフェストと違います。")
                cur.copy_expert(
                    sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER)").format(
                        sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(c) for c in columns)
                    ),
                    io.BytesIO(data),
                )
            import_data.resync_sequences(cur, tables)
            loaded = snapshot_export.read_snapshot(cur, label)[1]["snapshot_sha256"]
            if loaded != entry["snapshot_sha256"]:
                raise RuntimeError(f"{label}: 取り込んだ結果を書き出したハッシュがスナップショットと一致しません。")
            embeddings = fill_embeddings(cur, cache) if (label == "knowledge" and cache) else {}
            snapshot_state.write(cur, entry["snapshot_sha256"], kind="import", source=source)
        conn.commit()
        return {"embeddings": embeddings}
    except Exception:
        conn.rollback()
        raise


def run_snapshot_import(
    *,
    target: str,
    knowledge_url: str,
    conversation_url: str,
    timestamp: str,
    directory: "str | None" = None,
    bucket: "str | None" = None,
    prefix: str = "snapshot-import",
    rollback_prefix: str = "rollback",
    region: "str | None" = None,
    force: bool = False,
    cache_root: "str | None" = None,
    model_id: "str | None" = None,
) -> None:
    """スナップショットを取り込む。directory があればローカルから、無ければ s3://<bucket>/<prefix>/ から読む。"""
    if not directory and not bucket:
        raise RuntimeError("取り込み元がありません（IMPORT_DIR か IMPORT_BUCKET を指定してください）。")
    labels = import_data.parse_targets(target)
    urls = {"knowledge": knowledge_url, "conversation": conversation_url}
    s3 = None if directory else import_data._s3_client(region)
    where = directory if directory else f"s3://{bucket}/{prefix}/"
    print(f"{import_data._now()} ====== SNAPSHOT IMPORT start (ADR-0109, target={target}, from {where}).")

    cache = None
    if "knowledge" in labels and cache_root and model_id:
        cache = load_embedding_cache(cache_root, model_id)
        print(f"{import_data._now()} embedding cache ({model_id}): {len(cache) if cache else 'なし'}")

    for label in labels:
        url = urls[label]
        if not url:
            raise RuntimeError(f"{label} の接続 URL が未設定です。")
        entry, files = load_local(directory, label) if directory else load_s3(s3, bucket, prefix, label)
        verify_files(label, entry, files)
        print(f"{import_data._now()} [{label}] snapshot verified ({entry['snapshot_sha256'][:12]}…).")

        conn = psycopg2.connect(url)
        try:
            has_data = check_target(conn, label, entry, force=force)
            if has_data and s3 is not None:
                key = f"{rollback_prefix}/{label}/{timestamp}/{label}.sql"
                backup_sql = import_data.build_backup_sql(conn, label, import_data.tables_for(label))
                conn.rollback()
                import_data.upload_backup(s3, bucket, key, backup_sql)
                print(f"{import_data._now()} [{label}] rollback backup saved to s3://{bucket}/{key}.")
            elif has_data:
                print(f"{import_data._now()} [{label}] WARNING: ローカルからの取り込みのため、消す前の退避は取りません。")
            stats = import_database(conn, label, entry, files, cache=cache, source=f"{where} ts={timestamp}")
        finally:
            conn.close()
        rows = sum(t["rows"] for t in entry["tables"].values())
        print(f"{import_data._now()} [{label}] imported {len(entry['tables'])} tables / {rows} rows.")
        for table, (filled, remaining) in stats["embeddings"].items():
            print(f"{import_data._now()} [{label}] {table}: embeddings filled from cache {filled}, still NULL {remaining}")
    print(f"{import_data._now()} ====== SNAPSHOT IMPORT completed (target={target}).")
