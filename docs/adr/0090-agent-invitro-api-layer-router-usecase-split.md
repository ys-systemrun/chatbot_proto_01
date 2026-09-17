# ADR-0090: agent_invitro APIレイヤのルーター・ユースケース2層分離（server.pyの薄いアプリ組み立て役への縮退）

- ステータス: Accepted
- 日付: 2026-09-14
- 関連: `docs/requirement/202609141415_Agentic回答生成エンドポイント新設・APIレイヤ再構成要件定義書.md`, ADR-0032, ADR-0033, ADR-0043, ADR-0088, ADR-0089

## コンテキスト

`agent_invitro/src/main/api/server.py`は、ADR-0043で常駐HTTPサーバーを追加した時点では1エンドポイント（`/ask-pipeline`）＋ヘルスチェックの小さなファイルだったが、その後ADR-0084（会話タグ機構の廃止）・ADR-0085（`condensed_query`）・ADR-0086（Alias確定タグ）を経て約370行に育ち、次の5つの関心事を1ファイルに抱えている。

| 関心事 | 該当箇所 |
|---|---|
| API契約（スキーマ） | `Message` / `Summary` / `Request` / `Response` |
| コンポーネントの遅延初期化・DI | `_components` / `_init_lock` / `_get_components()` |
| ルーティング・例外処理 | `@app.post("/ask-pipeline")`の`ask()`、`@app.get("/health")` |
| 実処理 | `_ask_impl()` |
| ドメインヘルパー | `_extract_results()` / `_search_knowledge()` / `_build_context()` / `_summarize_oldest()` |

ADR-0088・ADR-0089により`/ask-agentic`を追加すると、Agenticループの実処理とそのヘルパーが更に積み上がり、どのヘルパーがどのエンドポイントに属するのかが判別できなくなる。同一リポジトリの`web_backend`は既に`main/app.py`（ルート定義）＋`main/controllers/*.py`（実処理）の2層構成を採っており（`chat_controller.py`冒頭コメント参照）、`agent_invitro`だけが単一ファイル構成のまま取り残されている。

制約が1つある。ADR-0043の決定により、AWS環境の`agent_invitro`は`terraform/main/app/main.tf`の`module "agent_invitro"`の`command`引数で常駐HTTPサーバーを起動しており、そこでモジュールパス（`agent_invitro.main.api.server:app`）が指定されている。再構成にあたってこのパスを変えると、Terraform側の変更とアプリ側の変更を同時にデプロイする必要が生じ、片方だけ適用された場合に起動不能になる。

## 決定

**`agent_invitro`のAPIレイヤを「薄いルーター（`main/api/routers/`）＋ユースケース層（`usecases/`）」の2層へ分離する。`main/api/server.py`は`create_app()`を呼び出して`app`を公開するだけのモジュールへ縮退させ、ファイル名・変数名は維持する。**

1. **ディレクトリ構成**（`src`平坦化方針、ADR-0032に従う）:

   ```
   agent_invitro/src/
   ├── main/api/
   │   ├── server.py          … 起動エントリポイント。create_app() を呼び app を公開するのみ
   │   ├── app.py             … create_app(): FastAPI 生成・router 登録・ロギング設定
   │   ├── schemas.py         … Message / Summary / Request / Response（全エンドポイント共通）
   │   ├── dependencies.py    … コンポーネントの遅延初期化・DI（現行 _get_components 相当）
   │   └── routers/
   │       ├── health.py      … GET /health
   │       ├── ask_pipeline.py… POST /ask-pipeline
   │       └── ask_agentic.py … POST /ask-agentic
   ├── usecases/
   │   ├── ask_pipeline.py    … 現行 _ask_impl 相当
   │   ├── ask_agentic.py     … Agenticループの起動と Response 組み立て
   │   └── conversation.py    … 要約畳み込み・history/next_order 算出・context 構築（共通）
   ├── graph/agentic_search.py… 探索ループの StateGraph（ADR-0088）
   ├── knowledge.py           … search_knowledge 呼び出しと結果パース（現行 _extract_results / _search_knowledge）
   ├── assess.py / clarify.py … 十分性評価・逆質問生成（ADR-0088）
   └── （既存）condense.py / generate.py / summarize.py / tags.py / config.py / llm.py / mcp_clients/
   ```

2. **`server.py`はモジュールパスを維持する**: Terraformの起動コマンドが参照する`agent_invitro.main.api.server:app`を変えないため、ファイル名と`app`という変数名を維持する。中身は`from .app import create_app`と`app = create_app()`に相当する数行のみとする。「エントリポイントのファイル名は変えずに中身だけを薄くする」ことで、アプリ側の変更をTerraformの変更と切り離してデプロイできる。

3. **ルーターの責務**: `APIRouter`を持ち、パス・HTTPメソッド・`response_model`の宣言、ユースケース関数の呼び出し、例外の`HTTPException`への変換のみを行う。ビジネスロジック（LLM呼び出し・MCP呼び出し・分岐）はルーターに書かない。現行`ask()`が持つ例外方針（`HTTPException`はそのまま透過、その他はスタックトレースをログ出力し`500`の`detail`に`{型名}: {メッセージ}`を含める）はルーター側の責務として維持する。

4. **ユースケース層の責務**: `fastapi`に依存しない。入出力には`schemas.py`のpydanticモデルをそのまま用いてよいが、`HTTPException`は送出しない（例外はそのままルーターへ伝播させ、ルーターでHTTPステータスへ変換する）。これによりMCP・Bedrock非接続のモックで単体テストできる。

5. **共通処理の共有**: `/ask-pipeline`と`/ask-agentic`で共通する処理（要約畳み込み・`history`/`next_order`算出・`context`構築・`search_knowledge`呼び出しと結果パース）は`usecases/conversation.py`・`knowledge.py`へ切り出し、重複実装しない。スキーマも`schemas.py`で共有する（ADR-0089 決定2）。

6. **DIの集約**: コンポーネントの遅延初期化（`load_settings()`・MCPツール取得・Bedrockクライアント生成）は`dependencies.py`に集約する。`asyncio.Lock`による初期化競合の防止、およびimport時に副作用を持たないという現行方針（ADR-0043 T9）を維持する。新設の十分性評価（`assess.py`）・逆質問生成（`clarify.py`）のクライアントもここで生成する。`load_settings()`の結果はここでプリミティブへ展開して各コンポーネントへ渡す（`Settings`を下位モジュールへ直接渡さない、ADR-0033の方針を踏襲する）。

7. **外部挙動の不変**: 本再構成によって`/ask-pipeline`・`/health`の外部から観測できる挙動（パス・スキーマ・ステータスコード・レスポンス内容・ログの主要項目）を変えない。再構成は`/ask-agentic`の追加とは独立してマージできる。

8. **層は2層まで**: ルーターとユースケースの2層とし、検索・タグ選定・生成をさらに`service`層へ切り出す3層構成は採らない。既存の`condense.py`・`generate.py`・`summarize.py`・`tags.py`・`knowledge.py`が既に機能単位のモジュールとして`src/`直下に平坦に並んでおり（ADR-0032）、これらが実質的なサービス群として機能している。

## 検討した代替案

- **エンドポイントごとに1ファイルを置き、ルーティングと実処理をまとめる（`api/routes/ask_pipeline.py`に全部書く）**: ファイル数が最小で、1エンドポイントの処理を1ファイルで読み切れる。しかしHTTP層（`HTTPException`・`response_model`）とビジネスロジックが混ざり、ユースケースの単体テストにFastAPIのテストクライアントが必要になる。またAgenticループのように実処理が大きいエンドポイントでは、結局ファイルが肥大化して現在の`server.py`と同じ問題を再生産する。`web_backend`が既に採っている「ルート定義とController の分離」とも不整合になるため不採用とした。

- **3層構成（router / usecase / service）**: 将来のエンドポイント追加には強い。しかし`src/`直下の既存モジュール（`condense.py`・`generate.py`・`summarize.py`・`tags.py`）が既にサービス相当の粒度で存在しており、その上にさらに`service/`ディレクトリを設けると、同じ役割のモジュールが2箇所に分散する。ADR-0032で`src/agent_invitro/`の入れ子を平坦化した経緯（階層を増やさない方針）とも逆行する。現在の規模には過剰と判断し不採用とした。

- **`server.py`を廃止し`main/api/app.py`をエントリポイントにする**: ファイル名と役割が一致して分かりやすい。しかしTerraformの`command`引数に指定されたモジュールパスの変更が必要になり、アプリのデプロイとTerraform applyの順序に依存が生じる（片方だけ適用されると起動不能になる）。得られる利益に見合わないため、`server.py`という名前を残して中身だけを薄くする方式を採った。

- **再構成を行わず`server.py`に`/ask-agentic`を追加する**: 変更量は最小だが、1ファイルが600行規模になり、`_ask_impl`（単発）と`_ask_agentic_impl`（ループ）およびそれぞれのヘルパーが同居する。ヘルパーの帰属が曖昧になり、共通化すべき処理と片方専用の処理の区別がつかなくなる。発注者から明示的に「`server.py`は薄いルーターのような形にして実処理をエンドポイントごとに分離したい」という要求が出ているため不採用とした。

## 結果・影響

- `agent_invitro/src/main/api/server.py`（約370行）が、`app.py`・`schemas.py`・`dependencies.py`・`routers/*.py`・`usecases/*.py`・`knowledge.py`へ分割される。`server.py`自体は10行程度になる。
- `terraform/main/app/main.tf`の`module "agent_invitro"`の`command`引数は変更不要である（モジュールパス`agent_invitro.main.api.server:app`が維持されるため）。
- `agent_invitro/Dockerfile`・ローカル`docker-compose.yml`は変更しない（ADR-0019・ADR-0043の「ローカルは`sleep infinity`」という位置づけを維持する）。
- `agent_invitro/README.md`のディレクトリ構成図・ファイル役割表・環境変数表を実態に合わせて更新する必要がある。
- 既存の`tests/`（`test_graph_smoke.py`・`test_condense.py`・`test_mcp_result_parsing.py`・`test_alias_match_text.py`・`test_config_llm.py`）は、`server.py`のプライベート関数を直接importしていないため、`knowledge.py`への移設に伴うimportパスの追随以外の変更は生じない見込みである。実装時に確認する。
- ユースケース層がFastAPIに依存しなくなることで、`/ask-pipeline`・`/ask-agentic`の実処理をMCP・Bedrock非接続のモックで単体テストできるようになる（REQ-202609141415 N-8.6）。
- `main/ipython/main.py`（IPython用エントリポイント、ADR-0019）は変更しない。`main/api/`とは独立したままである。
