# ADR-0021: LangGraphからMCPサーバー群への接続実装方式

- ステータス: Accepted
- 日付: 2026-08-06
- 関連: `docs/requirement/202608061621.md`, ADR-0022

## コンテキスト

LangGraphはMCP（Model Context Protocol）を直接扱う機能を持たないため、Knowledge MCP・Tag Selector MCPが提供するMCPツールをLangGraphのツールとして呼び出せるようにする接続部分（MCPクライアント／アダプタ層）の実装方式を決める必要がある。

主な選択肢は次の2つ。

- **(a) `langchain-mcp-adapters`**: LangChain公式が提供する薄いラッパーライブラリ。MCPサーバーの `tools/list` の結果を、LangChain/LangGraphの `Tool` オブジェクトへ自動的に変換する。`MultiServerMCPClient` により、複数のMCPサーバーへ同時接続し、両方のツールを1つのリストへ集約してエージェントへ束縛（bind）する処理を標準機能として持つ。転送方式はstdio・SSE・Streamable HTTPに対応する。
- **(b) MCP公式Python SDK（`mcp`）を直接利用**: `ClientSession` を用いて `initialize()` → `list_tools()` → `call_tool()` を直接呼び出す低レベルAPI。転送方式（stdio・SSE・Streamable HTTP）自体はSDKが提供するが、LangChain/LangGraphとの連携機能は持たず、MCPツールのJSON SchemaをLangGraphのツール呼び出し形式へ変換する処理や、複数MCPサーバー分のセッション管理・ツール集約処理は、いずれも自前で実装する必要がある。

当初はどちらを採るか未定としていた（要件定義書 Open Issue #2）が、両方式の詳細な比較を行ったうえで、発注者より(a)を採用する方針が確定した。

## 決定

**(a) `langchain-mcp-adapters` を採用する。**

Knowledge MCP・Tag Selector MCPの2サーバーへ `MultiServerMCPClient` で同時接続し、両サーバーが提供するツール（`select_tags` / `search_knowledge` 等）を自動変換してLangGraphのReActエージェント（ADR-0022）へそのまま束縛する構成とする。転送方式は既存2サーバーが採用するStreamable HTTPを使用する。

## 比較した内容・検討した代替案

| 観点 | (a) `langchain-mcp-adapters`（採用） | (b) MCP公式SDK直接利用 |
|---|---|---|
| ツールスキーマ変換（MCP Tool → LangGraphツール） | 自動（ライブラリが対応） | 自前実装が必要（JSON Schema変換を含む） |
| 複数MCPサーバーの集約 | `MultiServerMCPClient` で標準対応 | 自前でセッション管理・ツール集約が必要（同等機能なし） |
| Streamable HTTP対応 | 対応（既存2サーバーの転送方式と一致） | 対応（SDK自体の機能） |
| 依存関係 | LangChain/LangGraph一式に依存が増える（`agent_invitro` はLangGraphを前提としているため実質追加負担は小さい） | `mcp` パッケージのみで依存は最小 |
| 実装コスト（本プロジェクトの用途） | 低い。`create_react_agent` へそのまま束縛できる | 高い。変換層・集約層をすべて自作する必要がある |
| プロトコルの細部制御 | ライブラリの実装に委ねる | 自分で完全に制御できる |
| ライブラリの成熟度リスク | LangChain系の開発速度に追従する必要がある（対応MCPプロトコルバージョン等は実装時に再確認） | 公式SDKのため相対的に安定 |

(b)は依存を最小化でき、プロトコルの挙動を細部まで制御できる利点があるが、その利点が意味を持つのは「LangChain/LangGraphへの依存を避けたい」「MCPプロトコルの挙動を完全に自分で制御したい」といった場合に限られる。本プロジェクトの目的（Tag Selector MCP・Knowledge MCPの2サーバーに同時接続し、ReActエージェントにツールとして束縛する）に対しては、(a)の `MultiServerMCPClient` がほぼそのまま要求を満たす設計になっており、実装コストの差が大きいため、(a)を採用する。

「両方式を並行実装して比較する」案も検討したが、実験フェーズの目的（速く"動くこと"を確認する）に対して過剰であるため見送った。

## 結果・影響

- `agent_invitro` の依存関係に `langchain-mcp-adapters` およびLangChain/LangGraph関連パッケージが追加される。
- MCPクライアント層（要件定義書9.2節 `mcp_clients/`）の実装は、`MultiServerMCPClient` の設定（各MCPサーバーのURL・トランスポート種別の指定）が中心となり、スキーマ変換・複数サーバー集約のロジックを自前で書く必要はない。
- 外部ライブラリ（`langchain-mcp-adapters`）の対応MCPプロトコルバージョン・Streamable HTTP対応状況は、実装着手時に最新のドキュメントで再確認すること。ライブラリの更新でAPIが変わる可能性があるため、`agent_invitro` のバージョン固定（`pyproject.toml` でのバージョンピン）を推奨する。
- 将来、(a)で要件を満たせない事態（例: ライブラリの重大な不具合、Streamable HTTP対応の後退等）が判明した場合は、本ADRを改訂し(b)への切り替えを別途決定する。
