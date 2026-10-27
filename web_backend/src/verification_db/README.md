# web_backend/src/verification_db/ — 検証データ（verification_*）の永続化

検証機能（質問→タグ→情報源の検索精度検証）のデータを、conversation データベース（`CONVERSATION_DB_URL`）の `verification_question` / `verification_run` / `verification_run_tag` / `verification_run_source` の 4 テーブルに読み書きするモジュール（ADR-0048）。`main/controllers/verification_controller.py` から使われる。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | `VerificationDB` と各レコード dataclass を再エクスポートする。 |
| [`db.py`](db.py) | `VerificationDB`（psycopg2 のコンテキストマネージャー）。質問の一覧・詳細・作成・更新・削除・一括作成（CSV インポート用, ADR-0054）、検証実行結果（タグ・情報源を含む）の登録、評価の保存を行う。タグ／情報源は run_id をまとめた 1 クエリで取得する。 |
| [`models.py`](models.py) | `VerificationQuestionRecord`（質問と最新／全実行）、`VerificationRunRecord`（実行条件・状態・レイテンシ・評価）、`VerificationTagRecord`（選択タグ）、`VerificationSourceRecord`（取得した情報源）の dataclass 定義。 |
