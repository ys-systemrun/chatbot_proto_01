# ADR-0013: 管理UI（front_dev/web_backend）からのQA・タグ書き込み経路をKnowledge MCP経由に統一する

- ステータス: Accepted
- 日付: 2026-08-06
- 関連: ADR-0005, ADR-0006, ADR-0008, `docs/requirement/202608060826.md`

## コンテキスト

`docs/requirement/202608060826.md` にて、`front_dev` にQA・タグの一覧確認ページおよび登録編集機能を追加し、`web_backend` に対応するAPIを追加する要件を整理した。

`web_backend` は既存実装（`main.py`, `main_stateless.py`）において、`src/db.py` の `DB` クラスを介して `chatbot_db` へ直接クエリを発行する構成を既に持っている（`search_similar` 等）。そのため、新規追加するQA・タグの管理系APIについても、同様に `chatbot_db` への直接CRUDを `web_backend` 側に実装する方式が技術的には可能である。

一方、タグ（`tag`/`qa_tag`）に関する業務ロジック（循環参照防止の検証、`qa_tag`参照や子タグ存在時の削除拒否等）は、既にADR-0006の決定によりKnowledge MCP サーバの `TagRepository` に実装済みである。`web_backend` 側で同様のCRUDを独自実装すると、この業務ロジックを別コンポーネントに再実装することになり、将来どちらかの実装だけが更新され仕様がずれる（例: 循環参照チェックの条件が食い違う）リスクを抱える。

## 決定

`web_backend` に新設するQA・タグ管理系APIエンドポイント（`/api/qa/*`, `/api/tags/*`, `/api/categories`）は、**`chatbot_db` へ直接アクセスせず、すべてMCPクライアントとしてKnowledge MCP サーバのMCPツールを呼び出すことで実現する**。`web_backend` は、これらのエンドポインドに関しては「Knowledge MCP のMCPツールをREST APIとして`front_dev`向けに変換するBFF（Backend For Frontend）」として振る舞う。

読み取り系（一覧・詳細取得）・書き込み系（登録・編集・削除）のいずれについても、この方針を適用する。既存のチャット機能（`/ask`, `/ask-sl` 等、`search_similar` を用いた直接DB参照）は本決定の対象外とし、変更しない（並行運用を継続する）。

## 検討した代替案

- **`web_backend` が `chatbot_db` に対して直接CRUDを実装する方式**: 実装の見通しは立てやすいが、タグの循環参照防止・削除拒否等の業務ロジックをKnowledge MCPと`web_backend`の二箇所に重複実装することになり、保守コストと仕様不一致のリスクが大きいため見送った。将来QA側にも同様の業務ロジック（embedding再計算等、ADR-0014参照）が必要になることを踏まえると、この重複はさらに広がる。
- **`front_dev` が `web_backend` を介さず、Knowledge MCP のMCPエンドポイントを直接呼び出す方式**: ブラウザから MCP over HTTP（Streamable HTTP、セッション管理を伴う）を直接呼び出すことになり、プロトコルの複雑さ・CORS設定・認証方式の観点で難易度が高い。また既存 `front_dev` は常に `web_backend` を単一のバックエンドとして呼び出す構成（Vite dev proxy が `web_backend` にのみ転送する）であり、この既存構成からも逸脱するため見送った。

## 結果・影響

- `web_backend` に、Knowledge MCP のMCPエンドポイントへ接続するMCPクライアント実装が新たに必要になる（接続先URLは環境変数 `KNOWLEDGE_MCP_URL` として設定する）。
- Knowledge MCP側のMCPツールの入出力仕様（本ADR以降に追加するQA管理ツールを含む）が、`web_backend` のAPI仕様に直接影響する。ツールのインターフェース変更時は両コンポーネントを合わせて変更する必要がある。
- ADR-0006で決定された「Knowledge MCPは`tag`テーブルをキャッシュせず、外部からの直接変更にも追従する」設計は維持されるため、本決定により管理UI経由の変更が増えても、Tag Selector MCP等の既存コンポーネントの動作に追加の影響はない。
- `web_backend` のMCPクライアント実装方式（接続の都度張るか、プロセス内で維持するか等）の詳細は、要件定義書 Open Issue #4（本ADRに関連する13章 Open Issue 4）として詳細設計フェーズに委ねる。
