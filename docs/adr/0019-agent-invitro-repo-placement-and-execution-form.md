# ADR-0019: `agent_invitro`（Conversation Agent実験）の配置・実行形態

- ステータス: Accepted
- 日付: 2026-08-06
- 関連: `docs/requirement/202608061621.md`, ADR-0001, ADR-0002, ADR-0007

## コンテキスト

`docs/requirement/202608041002.md`・`docs/requirement/202608051636.md` はいずれも、Tag Selector MCP → Knowledge MCP の順に呼び出す「Conversation Agent（MCP Client）」の存在を前提としつつ、その実装をスコープ外としてきた。`agent_invitro/` はリポジトリ直下に空のスカフォールド（`src/main/`）として既に用意されている。

この Conversation Agent を LangGraph で実験的に実装するにあたり、Knowledge MCP（ADR-0001: モノレポ内新規ディレクトリ、ADR-0002: 独立Dockerコンテナ + HTTP/SSE）・Tag Selector MCP（ADR-0007: 同一方針を踏襲）と同様に、配置場所・実行形態を検討する必要がある。ただし今回の目的は「MCPホストとして正しく複数サーバーに接続しツールを呼び出せるか」を検証することであり、既存2サーバーのような常駐HTTPサーバー化は時期尚早である。

## 決定

- **配置**: 既存の `agent_invitro/` を維持し、リポジトリルート直下のコンポーネントとして、`knowledge_mcp/` や `tag_selector_mcp/` と並列に管理する（ADR-0001の方針を踏襲）。
- **実行形態**: 独立したDockerコンテナとして起動するが、常駐HTTPサーバーとはしない。`tty: true` によりコンテナを起動させ続け、開発者が `docker compose exec agent_invitro ipython` で接続し、LangGraphのグラフを対話的に手動実行して動作確認する形態とする。
- **対話シェルの実装**: **IPython を採用する**（発注者確認済み）。`agent_invitro` の依存パッケージ（`pyproject.toml`）に `ipython` を含め、コンテナに事前インストールしておく。Jupyter Labは追加のポート公開・認証設定が発生するため採用しない。
- **通信方式**: 既存2 MCPサーバーへは、docker-composeの内部ネットワーク経由でStreamable HTTP（`http://knowledge_mcp:8100/mcp`, `http://tag_selector_mcp:8200/mcp`）で接続する。ホスト側へのポート公開は行わない。

## 検討した代替案

- **常駐HTTPサーバー化（他MCPサーバーと同一パターン）**: 将来的には必要になるが、API仕様・会話状態管理・セッション管理等の設計判断が伴う。今回の目的（MCPホストとしての結線・ツール呼び出し可否の検証）に対しては過剰であり、実験フェーズの検証速度を優先して見送った。
- **ホスト側（コンテナ外）のPython環境で直接実行**: `knowledge_mcp` / `tag_selector_mcp` がdocker-compose内部ネットワークのサービス名で解決されることに依存しているため、コンテナ外から実行する場合はポートフォワード経由のURLへ変更する必要があり、他コンポーネントの起動手順との整合が取りづらい。将来の本番実装でも「独立コンテナ」が既定方針（ADR-0001, 0002, 0007）であるため、これに揃えた。
- **Jupyter Labサーバーとしてポート公開**: 対話的な使い勝手は良いが、追加のポート公開・認証設定が発生するため不採用と確定した（発注者確認済み、要件定義書 Open Issue #4解消）。

## 結果・影響

- `docker-compose.yml` / `.env`(.example) に `agent_invitro` サービスと関連環境変数（`KNOWLEDGE_MCP_URL`, `TAG_SELECTOR_MCP_URL` 等）が追加される。
- `knowledge_mcp` / `tag_selector_mcp` の healthy を前提に `depends_on` で起動順序を制御する必要がある。
- ホスト側へポートを公開しないため、既存2 MCPサーバーと同様の「社内ネットワーク限定公開」の考え方（README「セキュリティ」注記）よりもさらに閉じた構成となり、追加の認証検討は不要である。
- 将来、本番 Conversation Agent として常駐HTTPサーバー化する場合は、ADR-0002・ADR-0007と同様の方針であらためて実行形態を決定する（本ADRは実験フェーズのみを対象とする）。
- 既存スカフォールド（`agent_invitro/src/main/`）を要件定義書9.2節のディレクトリ構成案へどう揃えるかは、実装フェーズの判断とする（要件定義書 Open Issue #5）。
