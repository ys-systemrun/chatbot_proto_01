# ADR-0002: 実行形態・通信方式（独立コンテナ + HTTP/SSE）

- ステータス: Accepted
- 日付: 2026-08-04
- 関連: `docs/requirement/202608041002.md`

## コンテキスト

Knowledge MCP サーバの起動方式として、以下2案を比較した。

1. ローカルプロセスとして stdio 経由で起動し、LangGraph クライアントと1:1で密結合させる方式。
2. 独立した Docker コンテナとして常駐させ、HTTP/SSE（ないし Streamable HTTP）経由でMCP通信を行う方式。

chatbot_invitro は既に `docker-compose.yml` で `app` / `frontend` / `db` / `conversation_db` を独立コンテナとして運用している。また将来、既存 FastAPI app・将来の LangGraph エージェント・Tag Selector MCP サーバなど複数クライアントからの利用が見込まれる。

## 決定

Knowledge MCP サーバは **独立した Docker コンテナとして起動し、HTTP/SSE（Streamable HTTP）でMCP通信を行う**。`docker-compose.yml` に新規サービスとして追加し、既存 `db` サービスへネットワーク経由で接続する。

## 検討した代替案

- **stdio方式**: 実装・起動はシンプルだが、クライアントと1プロセスに紐づくため、複数クライアントからの同時利用や独立したスケーリング・監視がしにくい。将来のマルチクライアント化コストが高いと判断し見送った。

## 結果・影響

- 既存の `chatbot_app` / `chatbot_frontend` 等と同様の運用パターン（`docker compose ps` / `logs` / `healthcheck`）に統一できる。
- 複数クライアント（既存app、将来のLangGraphエージェント、Tag Selector MCPサーバ等）から同時に呼び出せる構成となる。
- ネットワーク経由となる分、stdio方式よりレイテンシがわずかに増える可能性があるが、Docker内部通信のため実用上の影響は小さいと想定する。
- 認証・アクセス制御の設計が新たに必要になる（要件定義書 Open Issue 参照）。
