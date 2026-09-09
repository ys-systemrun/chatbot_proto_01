"""トラブルシューティング記事 HTML のパース・冪等投入（ADR-0076 / ADR-0078 / REQ-202609071337 10章）。

2つの静的HTML文書（trouble_shooting.html / trouble_shooting_netauth.html）を <h2> 単位で
ブロック分割し、内包する <table>（現象・原因・案内内容 等）から構造化フィールドを抽出して
troubleshooting_article へ投入する。<table> を持たない手順書スタイルのブロックは guidance に
本文全体を格納し、他の構造化フィールドは NULL とする（10.1節）。いずれのケースでも body_html に
元HTMLブロック全体を保持する。

投入は (source_key, title) の一意性チェックによる冪等挿入とする（ADR-0018 / 10.2節）。既存レコードが
存在する場合は上書きしない（管理UI経由での手動編集・タグ付けを保護するため）。

パース系（parse_articles / build_embedding_text 等）は DB・embedding 非依存の純関数として実装し、
単体テスト可能にする。DB 投入（import_articles）は既存 (source_key, title) を先に取得し、未投入の
記事だけに embedding を計算して INSERT する（既存分の embedding 再計算を避ける）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

from bs4 import BeautifulSoup, Comment, Tag

# HTML の <table> 内 <th> ラベル（日本語）→ troubleshooting_article 列名（6.1節）。
LABEL_TO_FIELD = {
    "現象": "symptom",
    "操作履歴": "operation_history",
    "エラーコード": "error_code",
    "エラーメッセージ": "error_message",
    "システム環境": "system_environment",
    "ハードウェア環境": "hardware_environment",
    "バージョン情報": "version_info",
    "ユーザーに案内すべき内容": "guidance",
    "原因": "cause",
    "備考": "notes",
    "キーワード": "keyword_raw",
    "最終更新日時": "source_updated_at",
}

# INSERT 対象の構造化フィールド（id / embedding / created_at / updated_at を除く）。
ARTICLE_COLUMNS = [
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
]

# 最終更新日時のパース候補フォーマット（10.1節: パース失敗時は NULL とし、ログで気付けるようにする）。
_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d",
)


@dataclass
class TroubleshootingArticle:
    source_key: str
    title: str
    body_html: str
    guidance: str
    subtitle: Optional[str] = None
    symptom: Optional[str] = None
    operation_history: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    system_environment: Optional[str] = None
    hardware_environment: Optional[str] = None
    version_info: Optional[str] = None
    cause: Optional[str] = None
    notes: Optional[str] = None
    keyword_raw: Optional[str] = None
    source_updated_at: Optional[datetime] = None
    # パース時に検知した警告（最終更新日時のパース失敗など。運用側がログで気付けるようにする）。
    warnings: List[str] = field(default_factory=list)

    def to_insert_tuple(self) -> tuple:
        """ARTICLE_COLUMNS と同順の値タプルを返す（INSERT のプレースホルダ順に一致）。"""
        return (
            self.source_key,
            self.title,
            self.subtitle,
            self.symptom,
            self.operation_history,
            self.error_code,
            self.error_message,
            self.system_environment,
            self.hardware_environment,
            self.version_info,
            self.guidance,
            self.cause,
            self.notes,
            self.keyword_raw,
            self.body_html,
            self.source_updated_at,
        )


def _clean(value: Optional[str]) -> Optional[str]:
    """テーブルセル値を正規化する。空欄プレースホルダ（"-" / "‐" / "―" / 空）は None にする。"""
    if value is None:
        return None
    text = value.strip()
    if text in ("", "-", "‐", "―", "ー", "–", "—", "N/A", "n/a"):
        return None
    return text


def _parse_datetime(value: Optional[str]) -> tuple[Optional[datetime], Optional[str]]:
    """最終更新日時をパースする。失敗時は (None, 警告メッセージ) を返す（10.1節）。"""
    text = _clean(value)
    if text is None:
        return None, None
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt), None
        except ValueError:
            continue
    return None, f"最終更新日時のパースに失敗しました（NULL として投入）: {text!r}"


def _extract_table_fields(table: Tag) -> dict:
    """<table> の <tr><th>ラベル</th><td>値</td></tr> 行から構造化フィールドを抽出する。"""
    fields: dict = {}
    for row in table.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if th is None or td is None:
            continue
        label = th.get_text(strip=True)
        field_name = LABEL_TO_FIELD.get(label)
        if field_name is None:
            continue
        # 案内内容は複数段落を含みうるため改行区切りで結合する。
        value = td.get_text("\n", strip=True)
        fields[field_name] = value
    return fields


def _block_text(nodes: List[Tag]) -> str:
    """ブロック内ノード群のプレーンテキストを結合する（自由記述トピックの guidance 用）。"""
    parts = [n.get_text("\n", strip=True) for n in nodes]
    return "\n\n".join(p for p in parts if p).strip()


def build_embedding_text(article: TroubleshootingArticle) -> str:
    """埋め込み元テキストを組み立てる（ADR-0078 §8.3: title + subtitle + symptom + cause + guidance）。

    error_message・system_environment 等のノイズになりやすいフィールドは含めない。
    """
    parts = [
        article.title,
        article.subtitle,
        article.symptom,
        article.cause,
        article.guidance,
    ]
    return "\n".join(p for p in parts if p).strip()


def parse_articles(html: str, source_key: str) -> List[TroubleshootingArticle]:
    """HTML を <h2> 単位のトラブルシューティング記事へ分解する（10.1節）。

    - <h1> はドキュメント見出しとして無視する。
    - HTML コメント（テンプレート定義）は無視する。
    - <h2> がトピックの開始。次の <h2>（または末尾）までを1ブロックとする。<hr/> は区切りとして無視。
    - ブロック内に <table> があれば構造化フィールドを抽出。無ければ guidance に本文全体を格納。
    - <h3> があれば subtitle に先頭の1つを採用する。
    """
    soup = BeautifulSoup(html, "html.parser")
    # トップレベル要素を文書順に走査する（このHTMLは h2/table/p/ol 等がフラットな兄弟関係にある）。
    top_nodes = list(soup.children)

    articles: List[TroubleshootingArticle] = []
    current_title: Optional[str] = None
    current_nodes: List[Tag] = []

    def flush() -> None:
        if current_title is None:
            return
        articles.append(_build_article(source_key, current_title, current_nodes))

    for node in top_nodes:
        if isinstance(node, Comment):
            continue
        if not isinstance(node, Tag):
            continue
        name = (node.name or "").lower()
        if name == "h1":
            continue
        if name == "h2":
            flush()
            current_title = node.get_text(strip=True)
            current_nodes = []
        elif name == "hr":
            continue
        else:
            if current_title is not None:
                current_nodes.append(node)
    flush()

    # 空タイトルのブロックは投入対象外（テンプレート等の異常ブロック保険）。
    return [a for a in articles if a.title]


def _build_article(
    source_key: str, title: str, nodes: List[Tag]
) -> TroubleshootingArticle:
    warnings: List[str] = []

    # body_html: <h2> ブロック全体（見出し＋後続ノード）の元HTMLを保持する（6.1節フォールバック）。
    body_parts = [f"<h2>{title}</h2>"]
    body_parts.extend(str(n) for n in nodes)
    body_html = "\n".join(body_parts)

    # subtitle: 先頭の <h3>（ネストしている場合のみ。「Windows11」「TeamViewer」等）。
    subtitle = None
    for n in nodes:
        if (n.name or "").lower() == "h3":
            subtitle = n.get_text(strip=True) or None
            break

    table = next((n for n in nodes if (n.name or "").lower() == "table"), None)

    article = TroubleshootingArticle(
        source_key=source_key,
        title=title,
        body_html=body_html,
        guidance="",  # 後で確定させる
        subtitle=subtitle,
    )

    if table is not None:
        raw = _extract_table_fields(table)
        for field_name, value in raw.items():
            if field_name == "source_updated_at":
                dt, warn = _parse_datetime(value)
                article.source_updated_at = dt
                if warn:
                    warnings.append(warn)
            else:
                setattr(article, field_name, _clean(value))
        # guidance（NOT NULL）: 案内内容が空なら現象→本文→タイトルの順でフォールバック。
        guidance = article.guidance
        if not guidance:
            guidance = article.symptom or _block_text(nodes) or title
        article.guidance = guidance
    else:
        # 自由記述（手順書）スタイル: 本文全体を guidance に格納し、他の構造化フィールドは NULL。
        article.guidance = _block_text(nodes) or title

    article.warnings = warnings
    return article


# ---------------------------------------------------------------------------
# DB 投入（冪等: (source_key, title) 存在チェック, 10.2節）
# ---------------------------------------------------------------------------
def fetch_existing_state(conn) -> dict:
    """既存レコードの {(source_key, title): embedding_is_null(bool)} を返す。

    embedding_is_null=True の行は、ダンプ再インポート（chatbot.sql には embedding を
    含めない）直後などで embedding 未計算の状態。次回シードで埋め込みをバックフィルする。
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_key, title, embedding IS NULL FROM troubleshooting_article"
        )
        return {(sk, t): is_null for sk, t, is_null in cur.fetchall()}


def import_articles(
    conn,
    articles: List[TroubleshootingArticle],
    embed_fn: Callable[[str], List[float]],
) -> dict:
    """未投入の記事に embedding を計算して INSERT し、embedding 未計算の既存行はバックフィルする。

    - 新規（(source_key, title) 未存在）: embedding を計算して INSERT。
    - 既存 & embedding NULL: ダンプ再インポート直後等。embedding を計算して UPDATE（バックフィル）。
      本文・タイトル等はダンプ由来のものと HTML パース結果が一致する前提（同一原本）。
    - 既存 & embedding あり: 上書きしない（管理UIでの手動編集・タグ付けを保護, 10.2節）。

    Returns 統計（inserted / backfilled_embeddings / skipped_existing / warnings）。
    """
    existing = fetch_existing_state(conn)
    inserted = 0
    backfilled = 0
    skipped = 0
    all_warnings: List[str] = []

    placeholders = ", ".join(["%s"] * (len(ARTICLE_COLUMNS) + 1))  # +1 は embedding
    col_list = ", ".join(ARTICLE_COLUMNS) + ", embedding"
    insert_sql = (
        f"INSERT INTO troubleshooting_article ({col_list}) VALUES ({placeholders}) "
        "ON CONFLICT (source_key, title) DO NOTHING"
    )

    with conn.cursor() as cur:
        for article in articles:
            all_warnings.extend(article.warnings)
            key = (article.source_key, article.title)
            if key in existing:
                if existing[key]:  # embedding が NULL の既存行 → バックフィル
                    embedding = embed_fn(build_embedding_text(article))
                    cur.execute(
                        "UPDATE troubleshooting_article SET embedding = %s "
                        "WHERE source_key = %s AND title = %s AND embedding IS NULL",
                        (embedding, article.source_key, article.title),
                    )
                    backfilled += cur.rowcount
                else:
                    skipped += 1
                continue
            embedding = embed_fn(build_embedding_text(article))
            cur.execute(insert_sql, article.to_insert_tuple() + (embedding,))
            inserted += cur.rowcount
    conn.commit()
    return {
        "inserted": inserted,
        "backfilled_embeddings": backfilled,
        "skipped_existing": skipped,
        "warnings": all_warnings,
    }
