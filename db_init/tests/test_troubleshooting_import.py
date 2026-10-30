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
