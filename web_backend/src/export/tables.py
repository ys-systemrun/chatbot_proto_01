"""エクスポート対象テーブルの定義（IMPL-202608241600 T15、5.4 節）。

対象は chatbot データベース7テーブル・conversation データベース6テーブルの計13テーブル。
カラム定義は既存マイグレーション（db_hiroba_qa_init/migrations/0001〜0008 および
migrations_conversation/0001〜0003）に基づく（0006 で tag_folder / tag.folder_id 追加, ADR-0072、
0007 で tag_folder.parent_folder_id 追加・name UNIQUE 撤廃, ADR-0073、
0008 で tag / tag_folder に display_order 追加, ADR-0074）。
各テーブルについて次を保持する:

  - db          : データベース種別（"chatbot" / "conversation"）
  - name        : テーブル名
  - columns     : 全カラム（定義順。SQL 出力の INSERT に使う）
  - csv_exclude : CSV 出力から除外するカラム（question_altered.embedding のみ）
  - order_by    : 決定的な出力順のための ORDER BY 列（主キー）
  - _create_ddl : CREATE TABLE IF NOT EXISTS 文（既存マイグレーションと同一定義）

SQL 出力時の INSERT 順序（外部キー制約を満たす順序）は、下の CHATBOT_TABLES /
CONVERSATION_TABLES のリスト順で固定する（5.4 節）。
  - chatbot     : category → qa_original → tag_folder → tag → question_altered → tag_alias → qa_tag
                  → troubleshooting_article → troubleshooting_article_tag（ADR-0076）
  - conversation: conversation → message → verification_question → verification_run
                  → verification_run_tag → verification_run_source

ADR-0066: conversation の検証4テーブル（verification_*）を追加し、全データエクスポート／
全消去インポートが会話評価・検証データも含めて往復できるようにした（旧: conversation は
conversation / message の2テーブルのみ）。全消去インポート（ADR-0066）はここで定義する全13
テーブルを唯一の対象集合とし、バックアップ・TRUNCATE・再投入をこの集合で一致させる。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# question_altered.embedding の VECTOR 次元はモデル依存（AWS/Bedrock: 1024, ローカル:
# db_nomic 768 / db_multilingual 384）のため、CREATE TABLE の VECTOR(N) は固定できない。
# DDL 中の下記プレースホルダを、エクスポート時に実データベースから検出した次元で置換する
# （dump.detect_vector_dim）。検出できない場合の保険として EMBEDDING_DIM_PLACEHOLDER の既定値を使う。
EMBEDDING_DIM_PLACEHOLDER = "{embedding_dim}"
DEFAULT_EMBEDDING_DIM = 1024

# chatbot データベースの SQL ダンプ先頭に付ける拡張の宣言（question_altered.embedding 用）。
CHATBOT_SQL_HEADER = "CREATE EXTENSION IF NOT EXISTS vector;\n"


@dataclass(frozen=True)
class TableSpec:
    db: str
    name: str
    columns: list[str]
    order_by: list[str]
    _create_ddl: str
    csv_exclude: set[str] = field(default_factory=set)

    @property
    def csv_columns(self) -> list[str]:
        """CSV 出力に含めるカラム（csv_exclude を除いた columns）。"""
        return [c for c in self.columns if c not in self.csv_exclude]

    def create_ddl(self, embedding_dim: int | None = None) -> str:
        """CREATE TABLE IF NOT EXISTS 文を返す。VECTOR 次元プレースホルダを解決する。"""
        dim = embedding_dim if embedding_dim else DEFAULT_EMBEDDING_DIM
        return self._create_ddl.replace(EMBEDDING_DIM_PLACEHOLDER, str(dim))


# --------------------------------------------------------------------------- #
# chatbot データベース（migrations 0001〜0008 の最終形）
# --------------------------------------------------------------------------- #
CHATBOT_TABLES: list[TableSpec] = [
    TableSpec(
        db="chatbot",
        name="hiroba_category",
        columns=["id", "name"],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS hiroba_category (\n"
            "    id INTEGER PRIMARY KEY,\n"
            "    name TEXT\n"
            ");"
        ),
    ),
    TableSpec(
        db="chatbot",
        name="hiroba_qa_original",
        columns=["uuid", "question_text", "answer_text", "category_id", "title"],
        order_by=["uuid"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS hiroba_qa_original (\n"
            "    uuid TEXT PRIMARY KEY,\n"
            "    question_text TEXT,\n"
            "    answer_text TEXT,\n"
            "    category_id INTEGER,\n"
            "    title TEXT\n"
            ");"
        ),
    ),
    # タグフォルダマスタ（ADR-0072、ADR-0073 で階層化、ADR-0074 で display_order 追加）。
    # tag.folder_id の参照先のため tag より前に置く。parent_folder_id は自己参照。
    # name の UNIQUE は撤廃済み（ADR-0073 決定1: name は表示用ラベルで重複可）。
    TableSpec(
        db="chatbot",
        name="tag_folder",
        columns=["id", "name", "description", "parent_folder_id", "display_order"],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS tag_folder (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    name TEXT NOT NULL,\n"
            "    description TEXT,\n"
            "    parent_folder_id INTEGER REFERENCES tag_folder(id),\n"
            "    display_order DOUBLE PRECISION NOT NULL\n"
            ");"
        ),
    ),
    TableSpec(
        db="chatbot",
        name="tag",
        columns=[
            "id",
            "name",
            "parent_tag_id",
            "description",
            "folder_id",
            "display_order",
        ],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS tag (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    name TEXT NOT NULL UNIQUE,\n"
            "    parent_tag_id INTEGER REFERENCES tag(id),\n"
            "    description TEXT,\n"
            "    folder_id INTEGER REFERENCES tag_folder(id),\n"
            "    display_order DOUBLE PRECISION NOT NULL\n"
            ");"
        ),
    ),
    TableSpec(
        db="chatbot",
        name="hiroba_question_altered",
        columns=["id", "qa_id", "text", "embedding", "is_primary"],
        order_by=["id"],
        csv_exclude={"embedding"},
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS hiroba_question_altered (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    qa_id TEXT,\n"
            "    text TEXT,\n"
            f"    embedding VECTOR({EMBEDDING_DIM_PLACEHOLDER}),\n"
            "    is_primary BOOLEAN NOT NULL DEFAULT false\n"
            ");"
        ),
    ),
    TableSpec(
        db="chatbot",
        name="tag_alias",
        columns=["id", "tag_id", "alias"],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS tag_alias (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    tag_id INTEGER NOT NULL REFERENCES tag(id),\n"
            "    alias TEXT NOT NULL UNIQUE\n"
            ");"
        ),
    ),
    TableSpec(
        db="chatbot",
        name="hiroba_qa_tag",
        columns=["qa_id", "tag_id"],
        order_by=["qa_id", "tag_id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS hiroba_qa_tag (\n"
            "    qa_id TEXT NOT NULL REFERENCES hiroba_qa_original(uuid),\n"
            "    tag_id INTEGER NOT NULL REFERENCES tag(id),\n"
            "    PRIMARY KEY (qa_id, tag_id)\n"
            ");"
        ),
    ),
    # トラブルシューティング記事（ADR-0076 / migrations 0009）。tag（共有タグマスタ）の後に置く。
    # troubleshooting_article_tag は troubleshooting_article と tag の両方を参照するため両者より後。
    TableSpec(
        db="chatbot",
        name="troubleshooting_article",
        columns=[
            "id",
            "source_key",
            "title",
            "subtitle",
            "symptom",
            "operation_history",
            "error_code",
            "error_message",
            "system_environment",
            "hardware_environment",
            "version_info",
            "guidance",
            "cause",
            "notes",
            "keyword_raw",
            "body_html",
            "source_updated_at",
            "embedding",
            "created_at",
            "updated_at",
        ],
        order_by=["id"],
        csv_exclude={"embedding"},
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS troubleshooting_article (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    source_key TEXT NOT NULL,\n"
            "    title TEXT NOT NULL,\n"
            "    subtitle TEXT,\n"
            "    symptom TEXT,\n"
            "    operation_history TEXT,\n"
            "    error_code TEXT,\n"
            "    error_message TEXT,\n"
            "    system_environment TEXT,\n"
            "    hardware_environment TEXT,\n"
            "    version_info TEXT,\n"
            "    guidance TEXT NOT NULL,\n"
            "    cause TEXT,\n"
            "    notes TEXT,\n"
            "    keyword_raw TEXT,\n"
            "    body_html TEXT NOT NULL,\n"
            "    source_updated_at TIMESTAMP,\n"
            f"    embedding VECTOR({EMBEDDING_DIM_PLACEHOLDER}),\n"
            "    created_at TIMESTAMP NOT NULL DEFAULT now(),\n"
            "    updated_at TIMESTAMP NOT NULL DEFAULT now(),\n"
            "    UNIQUE (source_key, title)\n"
            ");"
        ),
    ),
    TableSpec(
        db="chatbot",
        name="troubleshooting_article_tag",
        columns=["article_id", "tag_id"],
        order_by=["article_id", "tag_id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS troubleshooting_article_tag (\n"
            "    article_id INTEGER NOT NULL REFERENCES troubleshooting_article(id),\n"
            "    tag_id INTEGER NOT NULL REFERENCES tag(id),\n"
            "    PRIMARY KEY (article_id, tag_id)\n"
            ");"
        ),
    ),
]


# --------------------------------------------------------------------------- #
# conversation データベース（migrations_conversation 0001〜0003 の最終形）
# --------------------------------------------------------------------------- #
CONVERSATION_TABLES: list[TableSpec] = [
    TableSpec(
        db="conversation",
        name="conversation",
        columns=["id", "created_at"],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS conversation (\n"
            "    id          VARCHAR PRIMARY KEY,\n"
            "    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()\n"
            ");"
        ),
    ),
    TableSpec(
        db="conversation",
        name="message",
        columns=[
            "id",
            "conversation_id",
            "order",
            "role",
            "evaluation",
            "input",
            "model",
            "content",
            "created_at",
        ],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS message (\n"
            "    id              VARCHAR PRIMARY KEY,\n"
            "    conversation_id VARCHAR NOT NULL REFERENCES conversation(id),\n"
            '    "order"         INTEGER NOT NULL,\n'
            "    role            SMALLINT NOT NULL,\n"
            "    evaluation      SMALLINT,\n"
            "    input           TEXT,\n"
            "    model           VARCHAR,\n"
            "    content         TEXT,\n"
            "    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),\n"
            '    UNIQUE(conversation_id, "order")\n'
            ");"
        ),
    ),
    # 検証機能の4テーブル（migrations_conversation/0002・0003, ADR-0048/0051/0060）。
    # tag_id / source_id は chatbot データベース側の値を参照するが、データベースを跨ぐ
    # 外部キー制約は張らない（ADR-0048）。ADR-0066 で全データエクスポート／インポートの
    # 対象に追加した。
    TableSpec(
        db="conversation",
        name="verification_question",
        columns=["id", "question_text", "memo", "created_at", "updated_at", "existing_tags"],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS verification_question (\n"
            "    id             SERIAL PRIMARY KEY,\n"
            "    question_text  TEXT NOT NULL,\n"
            "    memo           TEXT,\n"
            "    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),\n"
            "    updated_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),\n"
            "    existing_tags  TEXT\n"
            ");"
        ),
    ),
    TableSpec(
        db="conversation",
        name="verification_run",
        columns=[
            "id",
            "question_id",
            "question_text_snapshot",
            "executed_at",
            "status",
            "error_message",
            "max_tags",
            "confidence_threshold",
            "top_k",
            "min_score",
            "tag_selector_latency_ms",
            "knowledge_mcp_latency_ms",
            "evaluation",
            "evaluation_comment",
            "evaluated_at",
            "existing_tags_snapshot",
        ],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS verification_run (\n"
            "    id                        SERIAL PRIMARY KEY,\n"
            "    question_id               INTEGER NOT NULL REFERENCES verification_question(id) ON DELETE CASCADE,\n"
            "    question_text_snapshot    TEXT NOT NULL,\n"
            "    executed_at               TIMESTAMP WITH TIME ZONE DEFAULT NOW(),\n"
            "    status                    VARCHAR NOT NULL,\n"
            "    error_message             TEXT,\n"
            "    max_tags                  INTEGER,\n"
            "    confidence_threshold      REAL,\n"
            "    top_k                     INTEGER,\n"
            "    min_score                 REAL,\n"
            "    tag_selector_latency_ms   INTEGER,\n"
            "    knowledge_mcp_latency_ms  INTEGER,\n"
            "    evaluation                SMALLINT,\n"
            "    evaluation_comment        TEXT,\n"
            "    evaluated_at              TIMESTAMP WITH TIME ZONE,\n"
            "    existing_tags_snapshot    TEXT\n"
            ");"
        ),
    ),
    TableSpec(
        db="conversation",
        name="verification_run_tag",
        columns=["id", "run_id", "rank_no", "tag_id", "tag_name", "score", "path"],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS verification_run_tag (\n"
            "    id        SERIAL PRIMARY KEY,\n"
            "    run_id    INTEGER NOT NULL REFERENCES verification_run(id) ON DELETE CASCADE,\n"
            "    rank_no   INTEGER NOT NULL,\n"
            "    tag_id    INTEGER,\n"
            "    tag_name  VARCHAR NOT NULL,\n"
            "    score     REAL,\n"
            "    path      TEXT\n"
            ");"
        ),
    ),
    TableSpec(
        db="conversation",
        name="verification_run_source",
        columns=[
            "id",
            "run_id",
            "rank_no",
            "source_id",
            "source_type",
            "title",
            "content",
            "score",
            "metadata",
        ],
        order_by=["id"],
        _create_ddl=(
            "CREATE TABLE IF NOT EXISTS verification_run_source (\n"
            "    id           SERIAL PRIMARY KEY,\n"
            "    run_id       INTEGER NOT NULL REFERENCES verification_run(id) ON DELETE CASCADE,\n"
            "    rank_no      INTEGER NOT NULL,\n"
            "    source_id    VARCHAR,\n"
            "    source_type  VARCHAR,\n"
            "    title        TEXT,\n"
            "    content      TEXT,\n"
            "    score        REAL,\n"
            "    metadata     TEXT\n"
            ");"
        ),
    ),
]
