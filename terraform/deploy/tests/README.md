# terraform/deploy/tests — deploy パッケージのテスト

`terraform/deploy/src` の pytest テスト。実 AWS・terraform・dvc・git は実行せず、`aws` / `tf` / `proc` / `prompts` / `config` 等をスタブして呼び出し順や分岐を検証する。
`terraform/deploy` を作業ディレクトリにして `pytest` で実行する想定（`.dockerignore` によりイメージには含めない）。

## 構成

| 名前 | 説明 |
|---|---|
| [`test_config.py`](test_config.py) | `.env` の解析と環境変数への反映（クォート除去、コメント・空行、必須値欠落時のエラー、`AWS_PROFILE` の扱い） |
| [`test_tfvars.py`](test_tfvars.py) | 構成ごとの必須 `TF_VAR_*` 検査（不足分のみ報告、空値は欠落扱い、未知の構成名） |
| [`test_gate.py`](test_gate.py) | apply-all のゲート順序（database → app(0) → seed → app(1)） |
| [`test_app_stable_diagnostics.py`](test_app_stable_diagnostics.py) | 集約サービスの安定待機失敗時に、落ちたコンテナを名指しした診断を出すこと（ADR-0095） |
| [`test_migrate.py`](test_migrate.py) | migrate / `seed --skip-seed` が `MIGRATE_ONLY=true` で run-task を起動し確認を求めないこと（ADR-0075） |
| [`test_import.py`](test_import.py) | import-data の「ダンプアップロード → サービス停止 → IMPORT_MODE run-task → 再開」の順序と、失敗時の desired count 復元（ADR-0066） |
| [`test_query.py`](test_query.py) | query の `QUERY_MODE` オーバーライド、対象 DB 名のタイプ確認、CloudWatch Logs からの結果表示、不正入力のエラー（ADR-0083） |
| [`test_destroy_database.py`](test_destroy_database.py) | destroy-database の削除保護解除 apply を RDS だけに `-target` で絞ること、state の有無に応じたスキップ |
| [`test_kb_export.py`](test_kb_export.py) | kb-export（CSV スナップショットの取得・SHA-256 とデータベース全体のハッシュの照合・置き換え・dvc add, ADR-0109） |
| [`test_destroy_all.py`](test_destroy_all.py) | export-data / destroy-all（退避・SHA-256 照合・再開）と import-data のスキーマ版照合（ADR-0103） |
| [`test_kbdata.py`](test_kbdata.py) | DVC データの pull → status 検証と版の算出、差分・pull 失敗・`.dvc` 不在時のエラー（ADR-0097） |
| [`test_gitinfo.py`](test_gitinfo.py) | `GIT_COMMIT` / `GIT_DIRTY` の取得（未追跡・除外パスを dirty 判定から外す, ADR-0099） |
