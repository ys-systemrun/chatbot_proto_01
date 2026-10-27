# web_backend/ — 管理UI・チャット中継を担う FastAPI バックエンド（admin_ui）

ブラウザ（front_dev の SPA）から呼ばれる `/api/*` を提供する FastAPI アプリ。チャットは agent_invitro へ中継し（ADR-0045）、QA・タグ・言い換え・トラブルシューティング記事の管理は Knowledge MCP 経由で行う（ADR-0013）。会話評価・検証データは conversation データベースへ直接読み書きし、全データエクスポートも担う（ADR-0046 / ADR-0047）。AWS では front_dev のビルド成果物を同梱して静的配信も行う（ADR-0042）。

## 構成

| 名前 | 説明 |
|---|---|
| [`logs/`](logs/README.md) | アプリが実行時に書き出す日付別 JSONL ログの出力先（ローカル docker-compose でコンテナの `/app/logs` がここに当たる）。 |
| [`src/`](src/README.md) | アプリ本体の Python パッケージ（ルート定義・Controller・DB アクセス・MCP クライアント・LLM 呼び出し等）。 |
| [`Dockerfile`](Dockerfile) | ローカル docker-compose（`docker-compose.yml` の `web_backend` サービス）用イメージ。`pip install -e .` 後、`fastapi dev src/main/app.py` で開発サーバーを起動する。 |
| [`Dockerfile.admin_ui`](Dockerfile.admin_ui) | AWS の admin_ui サービス専用のマルチステージ Dockerfile（ADR-0042）。front_dev を本番ビルドして `static/` に同梱し、`fastapi run` で起動する。ビルドコンテキストはリポジトリルートで、deploy CLI から呼ばれる。 |
| [`pyproject.toml`](pyproject.toml) | パッケージ定義（`chatbot_invitro`）と依存ライブラリ、FastAPI エントリポイント `src.main.app:app`、CLI スクリプト（`debug` / `debug_question` / `evaluate`）の登録。 |
| [`results_per_query.csv`](results_per_query.csv) | 検索精度評価スクリプト `src/main/evaluate.py` の `--output` で出力したクエリ別 MRR 結果のサンプル（列: query, correct_qa, rank, reciprocal_rank。現行版は top1_distance 列も出力する）。 |
| [`serve.sh`](serve.sh) | `fastapi dev src/main/app.py --host 0.0.0.0` を実行するだけの開発サーバー起動スクリプト。 |

`pip install -e .` で生成される `chatbot_invitro.egg-info/` は .gitignore 対象のため載せていない。
