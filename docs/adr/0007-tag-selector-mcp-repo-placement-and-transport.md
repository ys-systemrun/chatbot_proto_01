# ADR-0007: Tag Selector MCP サーバの配置・実行形態（Knowledge MCPと同一方針を踏襲）

- ステータス: Accepted
- 日付: 2026-08-05
- 関連: `docs/requirement/202608051636.md`, ADR-0001, ADR-0002

## コンテキスト

Tag Selector MCP サーバを新規に立ち上げるにあたり、Knowledge MCP サーバ（ADR-0001: モノレポ内新規ディレクトリ、ADR-0002: 独立Dockerコンテナ + HTTP/SSE）と同様の論点（配置場所、実行形態・通信方式）を検討する必要があった。

- 既存リポジトリには、Knowledge MCP サーバの立ち上げによって整備済みの `docker-compose.yml` 運用パターン、`chatbot_db`（tag/tag_aliasを含む）、`.env` 運用ルールが既に存在する。
- Conversation Agent（将来のLangGraph Agent）は、Tag Selector MCP と Knowledge MCP サーバの両方を呼び出す構成となる（`docs/requirement/202608051636.md` 5.1節）。両サーバを独立コンテナとして同一の運用パターンに統一しておくことで、監視・デプロイの手間を増やさずに済む。

## 決定

Tag Selector MCP サーバは、Knowledge MCP サーバ（ADR-0001, ADR-0002）と同一の方針を踏襲する。

- **配置**: chatbot_invitro リポジトリのルート直下に新規ディレクトリ（例: `tag_selector_mcp/`）として追加する。既存の `app/`, `front_dev/`, `knowledge_mcp/` と並列のコンポーネントとして管理する。
- **実行形態・通信方式**: 独立した Docker コンテナとして起動し、HTTP/SSE（Streamable HTTP）でMCP通信を行う。`docker-compose.yml` に新規サービスとして追加する。

## 検討した代替案

- **独立した新規リポジトリとして作成する**（ADR-0001と同様の論点）: 将来の再利用可能性はあるが、現時点では chatbot_invitro 専用の利用にとどまるため、リポジトリ分割・権限管理・依存関係の二重管理といった初期コストが見合わない。
- **stdio方式で Conversation Agent プロセスに密結合させる**（ADR-0002と同様の論点）: 実装・起動はシンプルだが、Knowledge MCP サーバと同様に将来的な複数クライアントからの利用や独立したスケーリング・監視がしにくいため見送った。
- **Tag Selector MCP を Knowledge MCP サーバ内の1機能（追加ツール）として実装する**: `docs/requirement/202608041002.md` 参照資料の設計方針（「Knowledge MCPは検索実行に専念する」）、および同書 Open Issue #1（Tag Selector MCPは別コンポーネントとする前提）と整合しないため見送った。責務を分離しておくことで、将来タグ選択アルゴリズム（Embedding層・階層探索等）のみを差し替える際に Knowledge MCP へ影響が及ばない。

## 結果・影響

- 既存の `docker-compose.yml` / `.env` 管理・開発体制をそのまま拡張できるため、初期構築コストが低い。
- `tag_selector_mcp/` 配下は既存 `app/src` や `knowledge_mcp/` の実装を直接 import せず、DB接続情報・LLM API情報等の共有設定は `docker-compose.yml` / `.env` 経由でのみ受け渡す設計とし、将来の切り出しに備えて依存を最小化する。
- Tag Selector MCP と Knowledge MCP サーバの間に直接の通信・依存関係は発生しない（いずれも Conversation Agent から独立して呼び出される）。
- 認証・アクセス制御の設計が Knowledge MCP と同様に新たに必要になる（要件定義書 Open Issue 参照）。
