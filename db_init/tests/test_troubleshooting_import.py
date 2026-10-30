"""troubleshooting_import のパース純関数の単体テスト（ADR-0076 / 10章）。

DB / embedding には触れず、HTML → TroubleshootingArticle の分解・フィールド抽出・
最終更新日時パース・埋め込み元テキスト組み立てを検証する。
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import troubleshooting_import as ti


TABLE_HTML = """
<h1>ドキュメント見出し</h1>
<!-- テンプレートコメント（無視される） -->
<h2>マスタの読み込み時にエラー</h2>
<table border="1">
  <tbody>
    <tr><th>現象</th><td>マスタの読み込み時にエラー</td></tr>
    <tr><th>操作履歴</th><td>-</td></tr>
    <tr><th>エラーメッセージ</th><td>Operating system error 32</td></tr>
    <tr><th>ユーザーに案内すべき内容</th><td><p>バックアップソフトの例外に入れてください。</p></td></tr>
    <tr><th>原因</th><td>ファイルロック</td></tr>
    <tr><th>キーワード</th><td>マスタ ロック</td></tr>
    <tr><th>最終更新日時</th><td>2024-09-19 15:45</td></tr>
  </tbody>
</table>
<hr />
<h2>ファイアウォールの設定</h2>
<h3>Windows11</h3>
<ol><li>ファイアウォールを開く。</li><li>ポート1947を許可する。</li></ol>
"""


def test_parse_table_article_fields():
    arts = ti.parse_articles(TABLE_HTML, "trouble_shooting")
    assert len(arts) == 2

    a = arts[0]
    assert a.source_key == "trouble_shooting"
    assert a.title == "マスタの読み込み時にエラー"
    assert a.symptom == "マスタの読み込み時にエラー"
    assert a.operation_history is None  # "-" は None に正規化
    assert a.error_message == "Operating system error 32"
    assert a.guidance == "バックアップソフトの例外に入れてください。"
    assert a.cause == "ファイルロック"
    assert a.keyword_raw == "マスタ ロック"
    assert a.source_updated_at == datetime(2024, 9, 19, 15, 45)
    assert a.subtitle is None
    assert "<h2>マスタの読み込み時にエラー</h2>" in a.body_html
    assert a.warnings == []


def test_parse_freeform_article_uses_guidance_and_subtitle():
    arts = ti.parse_articles(TABLE_HTML, "trouble_shooting")
    b = arts[1]
    assert b.title == "ファイアウォールの設定"
    assert b.subtitle == "Windows11"  # 先頭の <h3>
    assert b.symptom is None  # テーブルなし → 構造化フィールドは NULL
    assert "ファイアウォールを開く" in b.guidance
    assert "ポート1947を許可する" in b.guidance


def test_h1_and_comment_ignored():
    arts = ti.parse_articles(TABLE_HTML, "x")
    titles = [a.title for a in arts]
    assert "ドキュメント見出し" not in titles


def test_guidance_fallback_when_table_has_no_guidance():
    html = """
    <h2>案内内容なしの記事</h2>
    <table><tbody>
      <tr><th>現象</th><td>症状だけある</td></tr>
    </tbody></table>
    """
    a = ti.parse_articles(html, "trouble_shooting")[0]
    # 案内内容が空なら現象へフォールバック（guidance は NOT NULL）。
    assert a.guidance == "症状だけある"


def test_parse_datetime_failure_records_warning():
    html = """
    <h2>日時が壊れている記事</h2>
    <table><tbody>
      <tr><th>ユーザーに案内すべき内容</th><td>本文</td></tr>
      <tr><th>最終更新日時</th><td>いつか</td></tr>
    </tbody></table>
    """
    a = ti.parse_articles(html, "trouble_shooting")[0]
    assert a.source_updated_at is None
    assert len(a.warnings) == 1
    assert "いつか" in a.warnings[0]


def test_build_embedding_text_uses_selected_fields():
    a = ti.TroubleshootingArticle(
        source_key="trouble_shooting",
        title="タイトル",
        body_html="<h2>タイトル</h2>",
        guidance="案内本文",
        subtitle="サブ",
        symptom="現象",
        cause="原因",
        error_message="ノイズになりやすいので含めない",
    )
    text = ti.build_embedding_text(a)
    assert text == "タイトル\nサブ\n現象\n原因\n案内本文"
    assert "ノイズ" not in text


def test_to_insert_tuple_matches_columns():
    a = ti.TroubleshootingArticle(
        source_key="trouble_shooting",
        title="t",
        body_html="b",
        guidance="g",
    )
    values = a.to_insert_tuple()
    assert len(values) == len(ti.ARTICLE_COLUMNS)
    assert values[0] == "trouble_shooting"
    assert values[ti.ARTICLE_COLUMNS.index("guidance")] == "g"


CSV_TEXT = (
    '"title","error_message","guidance","cause","notes","source_updated_at","source_page"\n'
    '"「CRCエラー」が発生する","CRCエラー","履歴を削除する。\n'
    'キャッシュを削除する。\n'
    '\n'
    '<b>や&はエスケープされる","","","2024-11-20 16:21:00","CRCエラー"\n'
    '"本文が空の行","","","","","",""\n'
    '"日時が壊れている行","","本文","","","いつか",""\n'
)


def test_parse_csv_articles_fields_and_body_html():
    arts = ti.parse_csv_articles(CSV_TEXT, "redmine_error_taiou")
    assert [a.title for a in arts] == ["「CRCエラー」が発生する", "日時が壊れている行"]  # 本文が空の行は除外

    a = arts[0]
    assert a.source_key == "redmine_error_taiou"
    assert a.error_message == "CRCエラー"
    assert a.guidance == "履歴を削除する。\nキャッシュを削除する。\n\n<b>や&はエスケープされる"
    assert a.cause is None  # 空欄は None に正規化
    assert a.source_updated_at == datetime(2024, 11, 20, 16, 21)
    assert a.body_html == (
        "<h2>「CRCエラー」が発生する</h2>\n"
        "<p>履歴を削除する。<br>\nキャッシュを削除する。</p>\n"
        "<p>&lt;b&gt;や&amp;はエスケープされる</p>"
    )
    assert a.warnings == []


def test_parse_csv_articles_warns_on_bad_datetime():
    a = ti.parse_csv_articles(CSV_TEXT, "redmine_error_taiou")[1]
    assert a.source_updated_at is None
    assert len(a.warnings) == 1


def test_parse_csv_articles_requires_title_and_guidance_headers():
    import pytest

    with pytest.raises(ValueError):
        ti.parse_csv_articles('"title","notes"\n"t","n"\n', "redmine_error_taiou")


def test_parse_csv_articles_reads_real_seed_csv_if_present():
    path = os.path.join(
        os.path.dirname(__file__), "..", "data", "redmine_error_taiou", "redmine_error_taiou.csv"
    )
    if not os.path.exists(path):
        import pytest

        pytest.skip("redmine_error_taiou.csv is not pulled (dvc pull)")
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    arts = ti.parse_csv_articles(text, "redmine_error_taiou")
    assert len(arts) == 29
    assert len({a.title for a in arts}) == len(arts)  # (source_key, title) の一意性
    assert all(a.warnings == [] for a in arts)

    import csv
    import io
    import uuid

    guids = [row["guid"] for row in csv.DictReader(io.StringIO(text))]
    assert len(set(guids)) == len(arts)  # 行ごとに異なる UUID
    assert all(uuid.UUID(g).version == 5 for g in guids)


def test_uuid_is_derived_from_source_key_and_title_for_html():
    arts = ti.parse_articles(TABLE_HTML, "trouble_shooting")
    a = arts[0]
    assert a.uuid == ti.derive_article_uuid("trouble_shooting", "マスタの読み込み時にエラー")
    assert a.uuid == ti.parse_articles(TABLE_HTML, "trouble_shooting")[0].uuid  # 何度パースしても同じ
    assert a.uuid != ti.derive_article_uuid("trouble_shooting_netauth", a.title)  # 出自が違えば別
    assert a.to_insert_tuple()[ti.ARTICLE_COLUMNS.index("uuid")] == a.uuid


def test_csv_uses_guid_column_as_uuid():
    text = '"guid","title","guidance"\n"11111111-2222-5333-8444-555555555555","t1","g"\n"","t2","g"\n'
    a, b = ti.parse_csv_articles(text, "redmine_error_taiou")
    assert a.uuid == "11111111-2222-5333-8444-555555555555"
    assert b.uuid == ti.derive_article_uuid("redmine_error_taiou", "t2")  # guid が空なら導出


class _FakeCursor:
    def __init__(self, rows, executed):
        self._rows = rows
        self._executed = executed
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._executed.append((sql, params))

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def cursor(self):
        return _FakeCursor(self.rows, self.executed)

    def commit(self):
        pass


def _article(title, uuid):
    return ti.TroubleshootingArticle(
        source_key="redmine_error_taiou", title=title, body_html="b", guidance="g", uuid=uuid
    )


def test_import_articles_backfills_uuid_of_existing_rows():
    # 既存行（embedding あり・uuid なし）→ uuid だけを埋め、embedding は計算しない。
    conn = _FakeConn([("redmine_error_taiou", "t1", False, None)])
    stats = ti.import_articles(conn, [_article("t1", "u-1")], embed_fn=lambda _: [0.0])
    assert stats["backfilled_uuids"] == 1
    assert stats["inserted"] == 0
    assert any("SET uuid" in sql and params[0] == "u-1" for sql, params in conn.executed)


def test_import_articles_skips_new_title_whose_uuid_is_already_used():
    # 元データでタイトルが変わった（uuid は同じ）→ 二重投入せず警告する。
    conn = _FakeConn([("redmine_error_taiou", "旧タイトル", False, "u-1")])
    stats = ti.import_articles(conn, [_article("新タイトル", "u-1")], embed_fn=lambda _: [0.0])
    assert stats["inserted"] == 0
    assert len(stats["warnings"]) == 1 and "u-1" in stats["warnings"][0]
    assert not any(sql.startswith("INSERT") for sql, _ in conn.executed)


def test_csv_uses_body_html_and_uuid_columns_when_present():
    text = (
        '"uuid","title","guidance","body_html"\n'
        '"u-1","t1","g","<h2>t1</h2><table><tr><th>原因</th><td>c</td></tr></table>"\n'
        '"","t2","g2",""\n'
    )
    a, b = ti.parse_csv_articles(text, "trouble_shooting")
    assert a.uuid == "u-1"
    assert a.body_html == "<h2>t1</h2><table><tr><th>原因</th><td>c</td></tr></table>"  # 元の HTML をそのまま使う
    assert b.uuid == ti.derive_article_uuid("trouble_shooting", "t2")
    assert b.body_html == "<h2>t2</h2>\n<p>g2</p>"  # 空なら guidance から組み立てる


def test_real_html_derived_csv_keeps_uuid_if_present():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "troubleshooting", "trouble_shooting.csv")
    if not os.path.exists(path):
        import pytest

        pytest.skip("trouble_shooting.csv is not pulled (dvc pull)")
    with open(path, encoding="utf-8-sig", newline="") as f:
        arts = ti.parse_csv_articles(f.read(), "trouble_shooting")
    assert len(arts) == 35
    # uuid は HTML 時代の導出値と同じ（出典 ID・ゴールデンセット v3 の正解を変えない, ADR-0107）
    assert all(a.uuid == ti.derive_article_uuid("trouble_shooting", a.title) for a in arts)
    assert "64ea266f-64ac-50ef-b82f-8ea7fd1db08d" in {a.uuid for a in arts}
