# ADR-0089: /ask-agentic の新設と既存 /ask-pipeline との併存（API契約は同一）

- ステータス: Accepted
- 日付: 2026-09-14（決定5を2026-09-15に改訂）
- 関連: `docs/requirement/202609141415_Agentic回答生成エンドポイント新設・APIレイヤ再構成要件定義書.md`, ADR-0043, ADR-0045, ADR-0088, ADR-0090

## 改訂履歴

| 日付 | 内容 |
|---|---|
| 2026-09-14 | 初版。切替は`web_backend`の環境変数`AGENT_INVITRO_ASK_PATH`による運用切替とした。 |
| 2026-09-15 | 発注者の指示により**決定5を改訂**。ブラウザ上のトグルで方式を選べる方式へ変更した（初版で「検証のためだけにUIを増やす」として不採用にした代替案の採用にあたる。REQ-202609141415 12章 Open Issue #3 のクローズ）。決定1〜4・6は変更しない。 |
| 2026-09-15 | 同日、発注者の指示により**決定5をさらに改訂**。`web_backend`の経路選択を「コントローラ内での環境変数による実行時分岐」から「ルート定義による静的なコントローラ分離」へ変更し、モードスイッチを兼ねていた環境変数`AGENT_INVITRO_URL`を廃止した（接続先アドレスは`AGENT_INVITRO_BASE_URL`へ改称）。同じくスイッチ用途だった`AGENT_INVITRO_ASK_PATH`も廃止した。**ADR-0045 決定1（`AGENT_INVITRO_URL`の設定有無による条件分岐）を上書きする。** |

## コンテキスト

ADR-0088により、`agent_invitro`にAgenticな回答生成（検索 → 十分性評価 → クエリ再定式化 → 再検索）を実装することが決まった。この新しい生成方式を、既存の`POST /ask-pipeline`にどう位置づけるかを決める必要がある。論点は2つある。

1. **エンドポイントを増やすか、既存を置き換えるか**: `/ask-pipeline`はADR-0043・ADR-0045により、`front_dev` → `web_backend`（admin_ui） → `agent_invitro`という中継経路上の契約として確立している。Agentic方式は`search_knowledge`の呼び出し回数・Bedrock呼び出し回数が増え、応答時間が伸びる可能性があり、また「関連情報が見つからない」場合の応答が定型の謝罪文から逆質問へ変わる（ADR-0088 決定6）。精度・レイテンシとも未検証の段階で既存経路を差し替えると、問題が出たときの切り戻しが難しい。

2. **API契約を拡張するか（trace等を返すか）**: Agenticループは「何周回したか」「どのクエリを試したか」「何が不足と判定されたか」という情報を内部に持つ。これをレスポンスに含めれば、ブラウザ上のデバッグ・検証がしやすくなる。一方で`Response{conversation_id, messages, summary}`はADR-0043で`web_backend`の実装と同一契約として維持されており、拡張すると`front_dev`の`domain/stateless/response.ts`・`StateContainer.tsx`、および`web_backend`の`chat_controller.py`の`Response`モデルにも変更が波及する。

発注者との協議（2026-09-14）により、「併存（`/ask-agentic`を新設）」「既存契約と同一」が選択された。切替方法については当初、環境変数による運用切替で足りると判断したが、2026-09-15に発注者から「画面上のトグルでパイプライン方式／エージェント方式を切り替えたい」との指示があり、決定5を改訂した（改訂履歴参照）。

## 決定

**`agent_invitro`に`POST /ask-agentic`を新設し、既存の`POST /ask-pipeline`と併存させる。両者のリクエスト・レスポンスのスキーマは完全に同一とし、Agenticループの経過（trace）はレスポンスには含めずサーバーログにのみ出力する。**

1. **併存**: `/ask-pipeline`は現行の生成方式（ADR-0043の単発プロンプト生成方式）のまま残す。本ADRでは廃止時期を定めない。`/ask-agentic`の精度・レイテンシを確認したうえで、非推奨化・削除を別途判断する（REQ-202609141415 12章 Open Issue #5）。

2. **API契約の同一性**: `/ask-agentic`は`Request{conversation_id, text, messages, summary}` → `Response{conversation_id, messages, summary}`、`Message{order, role, content, input, model, evaluation}`、`Summary{content, summarized_upto}`という既存契約をそのまま用いる。スキーマ定義は両エンドポイントで共有する（1つの`schemas.py`、ADR-0090）。

3. **応答の組み立ても同一形式**: `user`メッセージの`content`は`参考情報:\n{context}\n\n質問:\n{req.text}`、`assistant`メッセージは`input`（LLMへ渡したプロンプト）・`model`（`BEDROCK_CHAT_MODEL_ID`）・`evaluation=0`を設定する。`context`には全周回で得られた検索結果を統合したものを入れる。既存の会話評価機能（ADR-0045、`admin_ui`が`conversation`データベースへ直接書き込む）が、エンドポイントの違いを意識せずそのまま動作する。

4. **traceはログのみ**: 1リクエストにつき`conversation_id`・`condensed_query`・選定タグ・各周回の（周回番号／検索クエリ／ヒット件数／`sufficient`・`missing`・`next_query`）・最終の（総周回数／蓄積件数／`generate` or `clarify`／回答長）を`logger.info`で出力する。CloudWatchで1リクエスト分の探索経過を追跡できるようにする。

5. **切替方法（2026-09-15 改訂）**: **ブラウザ（`front_dev`）のヘッダーに「パイプライン方式 / エージェント方式」のトグルを置き、利用者が送信のたびに方式を選べるようにする。** `web_backend`には`POST /api/ask-agentic`を新設し、既存の`POST /api/ask-pipeline`と併せて2つのルートを持たせる。両ルートは同一の`chat_controller.ask()`を呼び、`agent_invitro`側の同名パスへ中継するだけで、リクエスト・レスポンスのスキーマは完全に同一である（決定2）。

   - トグルの選択値は`localStorage`（キー`chat_ask_mode_v1`）に保存し、リロード後も維持する。既定はパイプライン方式（現行動作）。不正値・未保存・`localStorage`参照不可のときは既定値へフォールバックする。
   - 選択は**次に送信する質問から**適用される。会話（`conversation_id`）は方式をまたいで継続でき、同一会話内で方式を切り替えたA/B比較もできる。応答待ちの間はトグルを無効化し、送信中の方式が入れ替わらないようにする。
   - **経路の選択はルート定義で静的に決まる**。`web_backend`の`chat_controller`は「LM Studio直接処理」専用に、新設の`agent_controller`は「`agent_invitro`への中継」専用にそれぞれ縮退させ、実行時に環境変数の有無で経路を出し分ける分岐は持たせない（ADR-0045 決定1 の上書き）。

     | `web_backend`のルート | コントローラ | 中継先 / 処理 |
     |---|---|---|
     | `POST /api/ask-pipeline` | `agent_controller.ask_pipeline()` | `agent_invitro`の`/ask-pipeline` |
     | `POST /api/ask-agentic` | `agent_controller.ask_agentic()` | `agent_invitro`の`/ask-agentic` |
     | `POST /api/ask-local` | `chat_controller.ask()` | `web_backend`内のLM Studio直接処理 |

   - 3ルートは同一のスキーマを共有する（`main/controllers/chat_schemas.py`へ切り出し）。ブラウザのトグルは前2者を呼び分ける。`/api/ask-local`はUIからは呼ばれず、ローカルでの直叩き用として残す。
   - **環境変数`AGENT_INVITRO_URL`は廃止する。** これは「接続先アドレス」と「中継するか直接処理するかのモードスイッチ（空文字か否か）」を兼ねており、経路がルート定義で決まる本方式では後者の役割が不要になるためである。接続先アドレスは`AGENT_INVITRO_BASE_URL`（既定`http://agent_invitro:8300`）へ改称し、`KNOWLEDGE_MCP_URL`・`TAG_SELECTOR_MCP_URL`と同じ「既定値を持つ接続先設定」に揃える。同じくスイッチ用途だった`AGENT_INVITRO_ASK_PATH`も廃止する（中継先パスはコントローラ内の定数）。
   - **既知の制約**: ローカル`docker-compose`の`agent_invitro`は`sleep infinity`でHTTPサーバーを起動しない（ADR-0019）ため、ローカルでは`/api/ask-pipeline`・`/api/ask-agentic`がともに502になる。ローカルでチャットを試す場合は`/api/ask-local`を直接叩くか、`agent_invitro`コンテナでUvicornを起動する。従来（`AGENT_INVITRO_URL`未設定時に暗黙でLM Studio経路へ落ちる挙動）からの明確な変更点である。

6. **`/health`は共通**: エンドポイントごとにヘルスチェックを分けない。ECSのコンテナヘルスチェックは引き続き`/health`（プロセス生存確認のみ、ADR-0043）を使う。

## 検討した代替案

- **`/ask-pipeline`をAgentic実装で置き換える（エンドポイントを増やさない）**: `front_dev`・`web_backend`とも無変更で済み、エンドポイントが1つに保たれる。しかしAgentic方式は応答時間が伸びうるうえ、「関連情報が見つからない」ときの応答が定型文から逆質問へ変わるという、利用者から見て明確な挙動変化を伴う。精度・レイテンシが未検証の段階で切り戻し手段を持たないのはリスクが高い。またA/B比較（同じ質問を両方式に投げて結果を比べる）ができなくなる。不採用とした。

- **併存させたうえで、`/ask-pipeline`の非推奨化・削除計画まで本ADRで定める**: 移行の見通しが立つ利点はあるが、Agentic方式の精度がまだ一度も測られていない段階で廃止期日を決めるのは根拠を欠く。発注者確認の結果、まず併存させ、比較結果を見て判断することとした。ただし恒久的に2系統を維持する意図ではないことを明記しておく（コードの重複はADR-0090の共通化により最小限に抑えられている）。

- **レスポンスに`trace`フィールドを追加する（必須または任意）**: 検証・デバッグには有用だが、`front_dev`の型定義・`web_backend`の`Response`モデルに変更が波及する。任意フィールドにすればクライアント無変更で済むものの、「使われないフィールドを契約に足す」ことになり、ADR-0043が守ってきた「`web_backend`と同一契約」という不変条件を崩す。探索経過はCloudWatchログで追える（決定4）ため、まずはログのみとした。ブラウザ上で経過を見たいという要求が実際に生じた場合に、改めて検討する。

- **`web_backend`側にも`/ask-agentic`パスを新設し、`front_dev`から明示的に選ばせる**: 画面上でトグルしてA/B比較できるようになる。`front_dev`・`web_backend`の両方に変更が必要で、検証のためだけにUIを増やすことになるため初版では不採用としたが、**2026-09-15に発注者の指示で本方式を採用した**（決定5）。同じ質問をその場で両方式へ投げ分けられること、環境変数の変更（＝ECSタスク定義の更新と再デプロイ）を伴わずに比較できることが、UIを1つ増やすコストを上回ると判断された。

- **環境変数`AGENT_INVITRO_ASK_PATH`のみで切り替える（初版の決定5）**: `front_dev`が無変更で済み、エンドポイントも増えない。しかしAWS環境で方式を切り替えるたびにタスク定義の更新と再デプロイが必要で、同じ質問を両方式へ投げ比べる検証が現実的に行えない。また切替がデプロイ単位になるため、「いつからどちらの方式か」を運用側が記録し続ける必要がある。上記の理由で不採用とし、環境変数も廃止した。

- **`AGENT_INVITRO_URL`による実行時分岐を残したまま、中継先パスだけをルートから渡す**: 変更量が最小で、ローカル`docker-compose`では暗黙にLM Studio経路へ落ちるという既存の利便性も保てる。しかし1つのコントローラ関数が「中継」と「LM Studio直接処理」という無関係な2実装を抱え続け、どちらが動くかがコードからは読み取れない（環境変数の値に依存する）。また`AGENT_INVITRO_URL`が「アドレス」と「モード」の2つの意味を持つため、AWS環境でアドレスを空にすると意図せずLM Studio経路（`chatbot`データベースへの直接クエリ）へ落ちるという危険な失敗モードがある。発注者の指示によりルート定義での静的分離を採用した。ローカルで暗黙にLM Studio経路へ落ちる挙動は失われるが、明示的な`/api/ask-local`で代替する。

## 結果・影響

- `agent_invitro`のエンドポイントは`GET /health`・`POST /ask-pipeline`・`POST /ask-agentic`の3つになる。ALBからの到達性は引き続き与えず、`admin_ui`からのVPC内部通信のみとする（ADR-0023・ADR-0043・ADR-0045を維持）。新規のポート・セキュリティグループルールは不要である（既存の8300番をそのまま使う）。
- `web_backend`に次の変更が生じる。中継のエラーハンドリング（`httpx.RequestError`→502、`4xx/5xx`の`detail`透過）の内容は変更せず、`agent_controller`へ移す。
  - `main/config.py`: `AGENT_INVITRO_URL`・`AGENT_INVITRO_ASK_PATH`の削除、`AGENT_INVITRO_BASE_URL`（既定`http://agent_invitro:8300`）の追加。`AGENT_INVITRO_TIMEOUT`は変更しない。
  - `main/controllers/chat_schemas.py`（新設）: `Message` / `Summary` / `Request` / `Response`。両コントローラが共有する。
  - `main/controllers/agent_controller.py`（新設）: `agent_invitro`への中継専用。`ask_pipeline()` / `ask_agentic()`。
  - `main/controllers/chat_controller.py`: 中継分岐を除去し、LM Studio直接処理専用へ縮退（`httpx`依存が無くなる）。
  - `main/app.py`: `POST /api/ask-agentic`・`POST /api/ask-local`ルートの追加と、`POST /api/ask-pipeline`の委譲先変更。
- `front_dev`に次の変更が生じる（初版の「`front_dev`には変更が生じない」は改訂により失効）。API契約（`Request` / `Response`の型）自体は不変であり、変更は呼び出し先パスの選択とUIに閉じる。
  - `domain/stateless/ask_mode.ts`（新設）: 方式の型・エンドポイント対応・ラベル・`localStorage`の読み書き。
  - `api.ts`: `askStateless(req, mode)`が`mode`に応じて`/api/ask-pipeline`・`/api/ask-agentic`を呼び分ける。
  - `feature/stateless/`（`StateContainer` / `LayoutContainer` / `Header`）: 方式stateの保持とトグルUI。
  - `style.css`: トグルのスタイル。
- `terraform/main/app/main.tf`の`module "admin_ui"`の環境変数を`AGENT_INVITRO_URL`から`AGENT_INVITRO_BASE_URL`へ改称する（値`http://agent_invitro:8300`は同じ）。**アプリ側の変更とTerraform側の変更を同時に適用する必要がある**（旧名のままだと既定値が使われる。値が同一であるため実害は出ない見込みだが、名前は揃えておく）。方式の切替自体は環境変数を経由しないため、`/ask-agentic`を使うために`terraform`を変更する必要はない。
- トグルはチャット画面（社内IP限定、ADR-0041）にのみ現れる。エンドユーザー向けの一般公開UIではないため、方式選択を利用者へ露出することの是非は問題にならない。
- 会話評価データ（`conversation`データベース）は、どちらのエンドポイントで生成された応答かを区別しない。**トグルにより方式が1会話・1メッセージ単位で混在しうるようになったため、この制約は初版よりも強く効く**（切替時刻による切り分けができない）。当面はA/B比較の対象を手元で記録する運用とし、集計が必要になった時点で`conversation`スキーマへの方式列の追加（ADR-0044の見直し）を検討する。
- 両エンドポイントの実処理は`usecases/ask_pipeline.py`・`usecases/ask_agentic.py`に分かれるが、要約畳み込み・`history`/`next_order`算出・`context`構築・`search_knowledge`呼び出しは共通モジュールを共有する（ADR-0090）。併存によるコード重複は限定的である。
