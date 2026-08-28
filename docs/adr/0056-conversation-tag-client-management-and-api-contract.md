# ADR-0056: 会話タグの管理主体とAPI契約（クライアントエコー方式、DB非永続化）

- ステータス: Accepted
- 日付: 2026-08-26
- 関連: `docs/requirement/202608261330_会話タグ管理機能要件定義書.md`, ADR-0043, ADR-0045, ADR-0049, ADR-0057

## コンテキスト

ChatbotUI（`POST /ask-sl`）の情報源検索精度を高めるため、会話で使ってきたタグ（「会話タグ」）を検索の絞り込みに使いたいという要望があった。ユーザーからは次の3点の方針が示された。

1. クライアント（ブラウザ）側で、この会話で使うタグをTypeScriptの状態として管理する。
2. リクエストで、クライアントが持つタグをbackendへ送り、情報源検索にもこのタグを利用する。
3. backendは、クライアントおよび`tag_selector_mcp`（`select_tags`）から得られたタグのうち、この会話で引き続き使うものを判定し、クライアントへ返す。

この方針を実現するにあたり、（a）会話タグをどこに・どの方式で保持するか（サーバー側DBか、クライアント側のみか）、（b）既存の`Request`/`Response`契約（`conversation_id, text, messages, summary` → `conversation_id, messages, summary`、ADR-0043）にどう組み込むか、という2点を決定する必要があった。

既存の`front_dev`（`StateContainer.tsx`）は、`summary`（会話要約）についてすでに同種の課題を解決済みである。`summary`はサーバー側DBに保存されず、`Response.summary`をReact stateとして保持し、次回リクエストの`Request.summary`にそのまま含めて送り返す「クライアントエコー方式」を採る。これにより、`agent_invitro`は`conversation`データベースへ一切アクセスしない（ADR-0043・ADR-0044の「`agent_invitro`は会話履歴にアクセスしない」という既存方針）という制約と両立している。

ユーザーへの確認の結果、会話タグについても「ブラウザ側のみで保持し、サーバーには保存しない」との回答を得た（要件定義書2章 回答4）。

## 決定

**会話タグは`summary`と同一の設計思想（クライアントエコー方式）で扱う。管理主体はクライアント（ブラウザ、React state）とし、`conversation`データベース等サーバー側のいかなる永続化も行わない。** `Request`/`Response`契約に`tags`フィールドを追加し、以下の3レイヤーすべてに変更を加える。

1. **`front_dev`**: `StateContainer.tsx`に`tags: ConversationTag[]`のReact stateを追加する。`Request.tags`に現在値を送信し、`Response.tags`が存在すれば置き換える。セッションリセット時は`[]`にリセットする（要件定義書6.1節）。
2. **`web_backend`（`src/main/controllers/chat_controller.py`）**: `Request`/`Response`Pydanticモデルに`tags`フィールドを追加する。ローカル`docker-compose`環境の直接処理ロジックは`tags`を一切参照しない（読み書きしない）。AWS環境の中継処理（`AGENT_INVITRO_URL`設定時）は、このフィールドを含めてそのまま転送・返却する（決定の技術的理由は「検討した代替案」および要件定義書6.3節を参照）。
3. **`agent_invitro`（`src/main/api/server.py`）**: `Request`/`Response`モデルに`tags`フィールドを追加し、ADR-0057が定める処理ロジック（`select_tags`とのマージ、継続タグ判定）を実装する。

`ConversationTag`の形式は次の通りとする。

```ts
export interface ConversationTag {
  id: number;
  name: string;
  score: number;        // backendが算出。クライアントは意味を解釈せずそのまま送り返す
  missed_turns: number;  // backendが算出（ADR-0057）。クライアントは意味を解釈せずそのまま送り返す
}
```

`score`・`missed_turns`はサーバー（`agent_invitro`）が算出する不透明な値であり、クライアントはこれを表示・加工する責務を持たない（表示UIは本ADRの対象外、要件定義書4.2節）。

## 検討した代替案

- **`conversation`データベースに会話タグを永続化する（`conversation_id`をキーに保存）**: 既存の会話評価データと同様の管理ができ、ブラウザを閉じても状態が失われない利点がある。しかし、（1）ユーザーから明確に「ブラウザ側のみでよい」との回答を得ていること、（2）`agent_invitro`は`conversation`データベースへ一切アクセスしないという既存方針（ADR-0043・ADR-0044）を破ることになり、新規のDB到達性・資格情報をAWS環境に追加する必要が生じること、（3）`summary`が同種の課題をクライアントエコー方式ですでに解決しており、設計の一貫性が保てること、の3点から不採用とした。
- **`web_backend`（中継層）にタグのマージ・判定ロジックを実装し、`agent_invitro`は関与しない**: `agent_invitro`への変更を避けられる利点があるが、情報源検索（`search_knowledge`）自体が`agent_invitro`内で行われるため、マージ結果を検索に反映させるには結局`agent_invitro`側にロジックが必要になる。中継層とロジック実装層が分かれることで実装が複雑になるため不採用とした。
- **`web_backend`（中継層）のスキーマ変更を行わず、`front_dev`から`agent_invitro`へ直接リクエストする**: ADR-0045が定めた「ブラウザから到達可能なAWSリソースは`admin_ui`のみであり、`agent_invitro`はVPC内部限定でALB非公開」という既存の境界（ADR-0023）を破ることになるため不採用とした。中継層への最小限のスキーマ追加（ロジックなし、パススルーのみ）で十分に要件を満たせる。

## 結果・影響

- `front_dev/src/domain/stateless/{request,response}.ts`、`StateContainer.tsx`に変更が発生する。新規に`ConversationTag`型を追加する。
- `web_backend/src/main/controllers/chat_controller.py`の`Request`/`Response`モデルに`tags`フィールド（オプショナル）を追加する。ローカル環境の処理ロジック本体（LM Studio呼び出し）には変更を加えない。
- `agent_invitro/src/main/api/server.py`の`Request`/`Response`モデルに`tags`フィールドを追加する。処理ロジックの詳細はADR-0057で定める。
- `conversation`データベース・`chatbot`データベースにはスキーマ変更が発生しない。
- ローカル`docker-compose`環境は、`chat_controller.py`のモデル変更（フィールド追加のみ）を除き、挙動が変化しない。`front_dev`は単一のビルドでローカル・AWS両環境に対応する（`Response.tags`が存在しない場合はクライアント側の値を保持する、要件定義書6.1節）。
- ブラウザを閉じる・タブを再読み込みすると会話タグは失われる。この制約は既存の`messages`・`summary`と同一であり、新たな制約ではない。
