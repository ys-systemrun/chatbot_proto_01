"""全データインポート（全消去→上書き）バッチ処理（ADR-0066）。

db_hiroba_qa_init を IMPORT_MODE で起動したときに実行される破壊的な処理。通常の
マイグレーション・冪等シード（ADR-0018）とは性質が正反対（全消去・要確認）のため、
main.py の起動モード分岐で明確に分離する。

処理（対象データベースごと）:
  1. 事前自動バックアップ（ADR-0066 §5）: 消去対象データを退避 SQL（TRUNCATE + INSERT）
     として生成し、S3 の rollback プレフィックスへ保存する。誤操作時の復旧手段。
  2. 全消去（§4）: 対象テーブルを 1 トランザクション内で TRUNCATE ... RESTART IDENTITY
     CASCADE する。
  3. 上書き投入（§4/§7）: S3 の import プレフィックスから取得した SQL ダンプ（エクスポート
     機能が生成した chatbot.sql / conversation.sql）を同一トランザクションで適用する。
     ダンプの CREATE EXTENSION / CREATE TABLE IF NOT EXISTS は既存スキーマに対して素通りし、
     テーブル定義は変更しない（本方式はエクスポート元と投入先が同一スキーマ状態であることを前提）。

全消去（TRUNCATE）と上書き投入を 1 トランザクションにまとめることで、投入途中の失敗時は
全消去ごとロールバックされ、投入前の状態に戻る（非機能要件「部分失敗時の扱い」）。

対象テーブルは web_backend/src/export/tables.py（全データエクスポート機能, ADR-0046/0047/0066）
と同一の集合・同一順序。バックアップ・TRUNCATE・再投入をこの集合で一致させる（§4）。
カラム・主キーは実データベースから introspection するため、列追加マイグレーションに追従する。
"""

from __future__ import annotations

from datetime import datetime

import boto3
import psycopg2
from psycopg2 import sql

# INSERT のバッチサイズ（web_backend/src/export/dump.py と同値）。
INSERT_BATCH_SIZE = 500

# 対象テーブル（親→子の順。FK 制約を満たす INSERT 順序。TRUNCATE は CASCADE で順不同可）。
# web_backend/src/export/tables.py の CHATBOT_TABLES / CONVERSATION_TABLES と一致させる（ADR-0066）。
CHATBOT_TABLES = [
    "hiroba_category",
    "hiroba_qa_original",
    "tag_folder",  # ADR-0072/0077: tag.folder_id の参照先のため tag より前
    "tag",
    "hiroba_question_altered",
    "tag_alias",
    "hiroba_qa_tag",
    # ADR-0076: トラブルシューティング記事（troubleshooting_article_tag は
    # troubleshooting_article と tag の両方を参照するため両者より後に置く）。
    "troubleshooting_article",
    "troubleshooting_article_tag",
]
CONVERSATION_TABLES = [
    "conversation",
    "message",
    "verification_question",
    "verification_run",
    "verification_run_tag",
    "verification_run_source",
]

VALID_TARGETS = ("chatbot", "conversation", "both")


def _now() -> datetime:
    # zoneinfo は 3.9+。import を関数内に遅延し、モジュール自体は古い環境でも import できる
    # ようにする（純関数の単体テストのため。実行イメージは python:3.11）。
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Tokyo"))


def parse_targets(target: str) -> list[str]:
    """target 文字列を処理対象データベースのラベル一覧へ正規化する。"""
    if target not in VALID_TARGETS:
        raise ValueError(
            f"IMPORT_TARGET は {VALID_TARGETS} のいずれかである必要があります: {target!r}"
        )
    if target == "both":
        return ["chatbot", "conversation"]
    return [target]


def tables_for(label: str) -> list[str]:
    return CHATBOT_TABLES if label == "chatbot" else CONVERSATION_TABLES


# ---------------------------------------------------------------------------
# introspection（カラム・主キー）
# ---------------------------------------------------------------------------
def _columns(cur, table: str) -> list[str]:
    """テーブルの全カラムを定義順（ordinal_position）で返す。"""
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def _pk_columns(cur, table: str) -> list[str]:
    """主キー列をキー内順序で返す。主キーが無ければ空リスト。"""
    cur.execute(
        """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
        WHERE i.indrelid = %s::regclass AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
        """,
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# バックアップ SQL の生成（退避用, ADR-0066 §5）
# ---------------------------------------------------------------------------
def dump_table_inserts(conn, table: str) -> str:
    """1テーブルをバッチ INSERT の SQL テキストとして返す（web_backend export と同方式）。

    値のエスケープは cur.mogrify に委ねる。embedding（VECTOR 型）は psycopg2 が文字列
    ("[...]") として返し、そのまま文字列リテラルとして INSERT すると pgvector が復元する。
    """
    with conn.cursor() as cur:
        cols = _columns(cur, table)
        if not cols:
            return f"-- {table}: テーブルが存在しません（スキップ）\n"
        order = _pk_columns(cur, table) or cols

        col_ident = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
        order_ident = sql.SQL(", ").join(sql.Identifier(c) for c in order)
        select_stmt = sql.SQL("SELECT {cols} FROM {tbl} ORDER BY {order}").format(
            cols=col_ident, tbl=sql.Identifier(table), order=order_ident
        )
        tbl_sql = sql.Identifier(table).as_string(conn)
        col_sql = col_ident.as_string(conn)
        placeholder = "(" + ", ".join(["%s"] * len(cols)) + ")"

        cur.execute(select_stmt)
        rows = cur.fetchall()

    parts: list[str] = []
    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        batch = rows[start : start + INSERT_BATCH_SIZE]
        with conn.cursor() as cur:
            values = ",\n".join(
                cur.mogrify(placeholder, row).decode("utf-8") for row in batch
            )
        parts.append(f"INSERT INTO {tbl_sql} ({col_sql}) VALUES\n{values};\n")
    if not parts:
        parts.append(f"-- {table}: 0 rows\n")
    return "".join(parts)


def build_backup_sql(conn, label: str, tables: list[str]) -> str:
    """消去対象データの退避 SQL を生成する（同一環境へ再適用して復旧できる形式）。

    先頭に TRUNCATE（誤インポート後の状態を消してから復旧するため）を置き、親→子の順で
    INSERT を並べる。CREATE TABLE は含めない（同一環境＝テーブルは存在する前提, §4）。
    """
    truncate = _truncate_statement(tables)
    header = (
        f"-- ADR-0066 rollback backup for '{label}' database\n"
        f"-- generated at {_now().isoformat()}\n"
        f"-- 復旧手順: この SQL を対象データベースへ psql -f 等で適用すると、\n"
        f"--   インポート直前のデータ状態へ戻せます（対象テーブル: {', '.join(tables)}）。\n\n"
    )
    parts = [header, truncate + "\n\n"]
    for table in tables:
        parts.append(dump_table_inserts(conn, table))
        parts.append("\n")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 全消去 + 上書き投入
# ---------------------------------------------------------------------------
def _truncate_statement(tables: list[str]) -> str:
    # テーブル名は本モジュールの固定リストのため、二重引用符での quote_ident で安全。
    quoted = ", ".join(f'"{t}"' for t in tables)
    return f"TRUNCATE {quoted} RESTART IDENTITY CASCADE;"


def resync_sequences(cur, tables: list[str]) -> None:
    """SERIAL / IDENTITY 列のシーケンスを MAX(値) へ同期する（pg_dump 相当, ADR-0066）。

    ダンプは id を明示 INSERT する一方、TRUNCATE ... RESTART IDENTITY でシーケンスが 1 に戻る。
    同期しないと、投入後にアプリが nextval で採る値（1..）が既存行の id と衝突する
    （例: create_tag → tag_pkey 重複）。投入直後・同一トランザクションで進めておく。

    setval(seq, MAX, is_called): 行があれば is_called=true で次の nextval は MAX+1、
    空テーブルなら MAX を 1・is_called=false として次の nextval は 1 になる。
    """
    for table in tables:
        cur.execute(
            """
            SELECT column_name, pg_get_serial_sequence(%s, column_name)
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table, table),
        )
        for col, seq in cur.fetchall():
            if not seq:  # シーケンス非依存の列（TEXT/UUID/通常列）はスキップ
                continue
            stmt = sql.SQL(
                "SELECT setval(%s, COALESCE((SELECT MAX({col}) FROM {tbl}), 1), "
                "(SELECT COUNT(*) FROM {tbl}) > 0)"
            ).format(col=sql.Identifier(col), tbl=sql.Identifier(table))
            cur.execute(stmt, (seq,))


def truncate_and_apply(conn, tables: list[str], dump_sql: str) -> None:
    """全消去（TRUNCATE）→ 上書き投入（ダンプ適用）→ シーケンス同期を 1 トランザクションで実行する。

    途中で失敗した場合はトランザクションごとロールバックされ、投入前の状態に戻る。
    """
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(_truncate_statement(tables))
            cur.execute(dump_sql)
            resync_sequences(cur, tables)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# S3 受け渡し
# ---------------------------------------------------------------------------
def _s3_client(region: str | None):
    return boto3.client("s3", region_name=region) if region else boto3.client("s3")


def fetch_dump(s3, bucket: str, key: str) -> str:
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read().decode("utf-8")


def upload_backup(s3, bucket: str, key: str, body: str) -> None:
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/sql; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------
def run_import(
    *,
    target: str,
    chatbot_url: str,
    conversation_url: str,
    bucket: str,
    import_prefix: str = "import",
    rollback_prefix: str = "rollback",
    region: str | None = None,
    timestamp: str | None = None,
) -> None:
    """全データインポート（全消去→上書き）を実行する（ADR-0066）。

    - target: "chatbot" / "conversation" / "both"
    - chatbot_url / conversation_url: 各データベースへの作業接続（migrator ロール推奨, §末尾）。
    - bucket: import/ ・ rollback/ を置く S3 バケット名。
    - import_prefix: 投入元ダンプの S3 プレフィックス（<prefix>/<label>.sql）。
    - rollback_prefix: 退避先の S3 プレフィックス（<prefix>/<label>/<ts>/<label>.sql）。
    """
    labels = parse_targets(target)
    ts = timestamp or _now().strftime("%Y%m%d%H%M%S")
    urls = {"chatbot": chatbot_url, "conversation": conversation_url}
    s3 = _s3_client(region)

    print(f"{_now()} ====== IMPORT MODE start (target={target}, bucket={bucket}, ts={ts}).")
    for label in labels:
        url = urls[label]
        if not url:
            raise RuntimeError(
                f"{label} の接続 URL が未設定です（対象に含めるには接続情報が必要）。"
            )
        tables = tables_for(label)
        dump_key = f"{import_prefix}/{label}.sql"
        backup_key = f"{rollback_prefix}/{label}/{ts}/{label}.sql"

        # 1. 投入元ダンプを先に取得（不備なら全消去前に失敗させる, §4 前提）。
        print(f"{_now()} [{label}] fetching import dump s3://{bucket}/{dump_key} ...")
        dump_sql = fetch_dump(s3, bucket, dump_key)
        print(f"{_now()} [{label}] import dump fetched ({len(dump_sql)} bytes).")

        # 2. 事前自動バックアップ（消去対象データの退避, §5）。
        print(f"{_now()} [{label}] building rollback backup ...")
        backup_conn = psycopg2.connect(url)
        try:
            backup_sql = build_backup_sql(backup_conn, label, tables)
        finally:
            backup_conn.close()
        upload_backup(s3, bucket, backup_key, backup_sql)
        print(f"{_now()} [{label}] rollback backup saved to s3://{bucket}/{backup_key}.")

        # 3. 全消去 + 上書き投入（1 トランザクション, §4）。
        print(
            f"{_now()} [{label}] TRUNCATE {len(tables)} tables + apply dump "
            "(single transaction) ..."
        )
        conn = psycopg2.connect(url)
        try:
            truncate_and_apply(conn, tables, dump_sql)
        finally:
            conn.close()
        print(f"{_now()} [{label}] import applied successfully.")

    print(f"{_now()} ====== IMPORT MODE completed successfully (target={target}).")
