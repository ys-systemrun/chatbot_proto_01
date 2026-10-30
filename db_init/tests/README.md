# db_init/tests — db_init の単体テスト

`db_init/src/` の純関数を pytest で検証します。DB・S3・embedding の外部呼び出しには触れません（モック／差し替え）。
各テストは `src/` を `sys.path` に追加して直接 import します。

## 構成

| 名前 | 説明 |
|---|---|
| [`test_embedding.py`](test_embedding.py) | `embedding.get_embedding` の provider 分岐（LM Studio / Bedrock）。boto3・requests をモックする |
| [`test_import_data.py`](test_import_data.py) | 全データインポート（ADR-0066）の対象テーブル解決・TRUNCATE 文の組み立て・コミット／失敗時ロールバック |
| [`test_export_data.py`](test_export_data.py) | 退避エクスポート（ADR-0103）の対象外テーブル検出・マニフェスト組み立て・ハッシュ・読み取りトランザクションの扱い |
| [`test_seed_helpers.py`](test_seed_helpers.py) | 広場 QA 本体の CSV の読み込み（列・カテゴリ ID の検証・BOM 付き）と、title 補完用レコードへの読み替え |
| [`test_troubleshooting_import.py`](test_troubleshooting_import.py) | トラブルシューティング記事 HTML のパース（記事分割・フィールド抽出・更新日時・埋め込み元テキスト）と、CSV の読み取り（列・`body_html` の組み立て・実データの一意性）、uuid の導出とシード時のバックフィル・重複検知 |
