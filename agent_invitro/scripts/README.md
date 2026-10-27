# agent_invitro/scripts — 手動実行の確認スクリプト

コンテナ内で `python -m scripts.<名前>` として手動で実行する確認用スクリプトを置きます。HTTP サーバーやテストからは呼ばれません。

## 構成

| 名前 | 説明 |
|---|---|
| [`check_tool_calling.py`](check_tool_calling.py) | Phase 1 スモークテスト。LM Studio のロード済みモデルにダミーツール（`get_weather`）を `bind_tools()` で束縛して問い合わせ、構造化された `tool_calls` を返せるか（対応／非対応）を標準出力に出す。`docker compose exec agent_invitro python -m scripts.check_tool_calling` で最初に実施する（ADR-0020 / ADR-0022 の前提確認）。 |

※ `__pycache__/` は .gitignore 対象のため載せていません。
