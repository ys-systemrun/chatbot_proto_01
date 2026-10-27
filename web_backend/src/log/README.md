# web_backend/src/log/ — 日付別 JSONL ロガー

検索・回答生成・管理UI操作・エクスポートの記録を、`LOG_DIR`（既定 `logs`）配下の `YYYY-MM-DD.jsonl` に追記するモジュール。書き込み失敗は標準出力に出すだけで処理は止めない。出力例は [`web_backend/logs/`](../../logs/README.md)。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | ロガー本体。`log_search` / `log_format_query` / `log_generate`（`chat_controller` が使用）、`log_admin_operation`（QA・タグ・言い換え・トラブルシューティング・検証の各 Controller が使用。操作者は記録しない）、`log_export`（`export_controller` が使用）を提供する。 |
