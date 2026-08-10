# ADR-0001: Knowledge MCP サーバの配置（モノレポ構成）

- ステータス: Accepted
- 日付: 2026-08-04
- 関連: `docs/requirement/202608041002.md`

## コンテキスト

ナレッジベース検索を提供する Knowledge MCP サーバを新規に立ち上げるにあたり、既存の chatbot_invitro リポジトリに追加するか、独立した新規リポジトリとするかを検討する必要があった。

- 既存リポジトリには、Knowledge MCP サーバが再利用する pgvector 済み PostgreSQL（`chatbot_db`）、embedding 用 LM Studio 連携、docker-compose 構成、`.env` 運用ルールなど、流用可能な資産が既に存在する。
- 一方、将来的に他プロジェクトからも Knowledge MCP サーバを再利用したい可能性もある。

## 決定

Knowledge MCP サーバは、**chatbot_invitro リポジトリのルート直下に新規ディレクトリ（例: `knowledge_mcp/`）として追加する**。既存の `app/`, `front_dev/` と並列のコンポーネントとして管理する。

## 検討した代替案

- **独立した新規リポジトリとして作成する**: 将来の再利用や独立したCI/CD・バージョニングがしやすい一方、現時点では chatbot_invitro 専用の利用にとどまるため、リポジトリ分割・権限管理・依存関係の二重管理といった初期コストが見合わない。

## 結果・影響

- 既存の `docker-compose.yml` / `.env` 管理・開発体制をそのまま拡張できるため、初期構築コストが低い。
- `knowledge_mcp/` 配下は既存 `app/src` を直接 import せず、DB接続情報・embedding API情報等の共有設定は `docker-compose.yml` / `.env` 経由でのみ受け渡す設計とし、将来の切り出しに備えて依存を最小化する。
- 将来、他プロジェクトへの提供や独立運用が必要になった場合は、`git subtree` 等を用いた切り出し作業が別途発生する。
