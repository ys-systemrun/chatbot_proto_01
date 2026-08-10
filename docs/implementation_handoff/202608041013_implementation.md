# ナレッジベース MCP サーバ 実装指示書

- 文書番号: IMPL-202608041013
- 対象プロジェクト: chatbot_invitro / Knowledge MCP サーバ
- 参照文書:
  - 要件定義書 `docs/requirement/202608041002.md`（REQ-202608041002）
  - ADR `docs/adr/0001〜0005`
- 本書の位置づけ: 要件定義書・ADRで確定した方針を、実装担当者（開発者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。本書自体はソースコードを含まない（インターフェース仕様・作業手順・設定値の指示にとどめる）。実装は別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確定した事項

要件定義書の Open Issues のうち、実装着手には確定が必要だが未決だった項目について、以下の通り値を定めた。**本節の内容は発注者により承認済み。**

| 項目 | 決定内容 | 理由・備考 |
|---|---|---|
| tags のスキーマ表現（Open Issue #5） | **ADR-0005にて確定**: `tag` マスタテーブル（`parent_tag_id` による自己参照）＋ `qa_tag` 関連テーブルによるリレーショナル構造とする。`qa_original` には `tags` カラムは追加しない | 将来的なタグの木構造化・タグ単体の管理（リネーム等）に対応するため。以降の節はこの構造を前提に更新済み |
| スコア変換式 | `score = 1 / (1 + distance)` （`distance` はpgvector `<=>` の値） | 暫定式。distanceは小さいほど類似度が高い。要精度検証・調整 |
| MCPトランスポートの具体形式 | Streamable HTTP | ADR-0002（HTTP/SSE方針）の具体化。既存/新規MCPクライアント双方との互換性を優先 |
| `top_k` デフォルト値 | 5 | 既存 `search_similar` の呼び出し実績（top_k=3）より広めに設定。要検証 |
| `KNOWLEDGE_MCP_PORT` デフォルト値 | 8100 | 既存の `BOT_PORT(8000)` 等と衝突しないポート |
| 認証方式（Open Issue #4） | 本フェーズでは追加認証を実装せず、Docker内部ネットワーク限定公開（ホスト側ポート公開は開発時のみ）で運用する | 恒久対応ではない。Open Issue #4として継続管理 |
| タグマスタの管理方式（Open Issue #9、ADR-0006） | `list_tags`/`create_tag`/`rename_tag`/`move_tag`/`delete_tag` をKnowledge MCPツールとして提供する。`tag`テーブルはキャッシュせず都度DB参照とし、外部からの直接管理とも共存できる設計とする | 発注者の指示により決定。書き込み系ツールのアクセス制御は別途Open Issue #10として管理 |

## 1. 全体進行フェーズ

| Phase | 目的 | 主な成果物 | 前提 |
|---|---|---|---|
| Phase 0 | 事前準備 | 作業ブランチ、ディレクトリ雛形 | なし |
| Phase 1 | DBスキーマ移行 | `title`/`tags` カラム追加、既存データ補完 | Phase 0 |
| Phase 2 | ドメインモデル・Repository層 | `Document`, `Repository` 抽象, `QARepository` | Phase 1 |
| Phase 3 | SearchService | Repository集約・スコア整形 | Phase 2 |
| Phase 4 | MCP Tool層 | `search_knowledge` ツール定義・サーバ起動 | Phase 3 |
| Phase 5 | Docker統合 | `docker-compose.yml` 追記、`.env` 追記、Dockerfile | Phase 4 |
| Phase 6 | 検証・受け入れ | MRR比較、疎通確認、DoDチェック | Phase 5 |

以降の各節は、この順序で実施することを前提に指示する。後続フェーズは前フェーズの成果物を前提とするため、順序を入れ替えないこと。

## 2. WBS（作業分解構成）

| No. | タスク | Phase | 参照 | 成果物 |
|---|---|---|---|---|
| T1 | `knowledge_mcp/` ディレクトリ雛形作成（3節のディレクトリ構成通り） | 0 | ADR-0001 | ディレクトリ一式 |
| T2 | `qa_original` へ `title TEXT` カラム追加 ＋ `tag`/`qa_tag` テーブル新設スクリプト作成 | 1 | 要件7.3, ADR-0003, ADR-0005 | マイグレーションSQL |
| T3 | 既存投入データ（`data/exportjson_withguid.json`）からtitle値の補完、タグマスタ(`tag`)投入、QA-タグ紐付け(`qa_tag`)投入を行うバッチ作成 | 1 | 要件7.3, ADR-0005 | 補完バッチ（1回限りの投入スクリプト、2段階処理） |
| T4 | `Document` データモデル定義 | 2 | 要件6.2 | `models/document.py` 相当のシグネチャ |
| T5 | `Repository` 抽象基底クラス定義 | 2 | 要件6.2 | `repository/base.py` 相当のシグネチャ |
| T6 | `QARepository` 実装指示（既存 `search_similar` を移植・拡張） | 2 | 要件6.3 | `repository/qa_repository.py` 相当のシグネチャ |
| T7 | `SearchService` 実装指示 | 3 | 要件6.4 | `services/search_service.py` 相当のシグネチャ |
| T8 | `search_knowledge` MCPツール定義・入出力スキーマ実装指示 | 4 | 要件6.1 | `mcp/tools.py`, `mcp/schemas.py` 相当のシグネチャ |
| T9 | MCPサーバ起動エントリポイント実装指示（Streamable HTTP） | 4 | ADR-0002 | `main.py` 相当のシグネチャ |
| T10 | ヘルスチェック手段の実装指示 | 4 | 要件8 | ヘルスチェックエンドポイント/リソース仕様 |
| T11 | `Dockerfile` 作成指示 | 5 | ADR-0002 | Dockerfile仕様 |
| T12 | `docker-compose.yml` / `.env.example` 追記指示 | 5 | 要件9 | 差分内容 |
| T13 | MRR比較検証（既存 `evaluate` と比較） | 6 | 要件11 | 比較結果レポート |
| T14 | 手動疎通確認（MCPクライアントからの呼び出し） | 6 | 要件11 | 確認結果 |
| T15 | DoDチェックリスト実施 | 6 | 要件11 | チェック結果 |
| T16 | `TagRepository` 実装指示（tag/qa_tagテーブルへのCRUD） | 2 | 要件6.6, ADR-0006 | `repository/tag_repository.py` 相当のシグネチャ |
| T17 | タグ管理MCPツール（`list_tags`/`create_tag`/`rename_tag`/`move_tag`/`delete_tag`）定義・入出力スキーマ実装指示 | 4 | 要件6.6, ADR-0006 | `mcp/tools.py`, `mcp/schemas.py` への追加分 |
| T18 | 循環参照防止バリデーション実装指示（`create_tag`/`move_tag`） | 4 | ADR-0006 | バリデーションロジック仕様（5.6節） |
| T19 | タグ管理ツールの単体テスト観点整理 | 6 | 要件11 | テストケース一覧（9.4節） |
| T20 | タグ管理ツールのアクセス制御方針の暫定整理（Open Issue #10） | 6 | 要件13 | 暫定運用ルールのドキュメント化 |

## 3. ディレクトリ・ファイル構成指示

```
chatbot_invitro/
└── knowledge_mcp/
    ├── Dockerfile
    ├── pyproject.toml            … 依存関係定義（mcp SDK, psycopg2, requests 等）
    ├── src/
    │   └── knowledge_mcp/
    │       ├── __init__.py
    │       ├── main.py           … エントリポイント。MCPサーバをStreamable HTTPで起動（T9）
    │       ├── mcp/
    │       │   ├── server.py     … MCPサーバインスタンス生成・ツール登録
    │       │   ├── tools.py      … search_knowledgeツールのハンドラ定義（T8）
    │       │   └── schemas.py    … 入出力のJSON Schema／型定義（T8）
    │       ├── services/
    │       │   └── search_service.py   … SearchService実装（T7）
    │       ├── repository/
    │       │   ├── base.py             … Repository抽象基底クラス（T5）
    │       │   ├── qa_repository.py    … QARepository実装（T6）
    │       │   └── tag_repository.py   … タグマスタCRUD実装（T16）。tagテーブルをキャッシュせず都度DBを参照する
    │       ├── models/
    │       │   └── document.py         … Document データモデル（T4）
    │       └── db/
    │           └── connection.py       … 既存chatbot_dbへの接続（既存app/src/db.pyのDB接続部分に準拠）
    ├── migrations/
    │   ├── 0001_add_title_and_tag_tables.sql   … T2（title列追加 + tag/qa_tagテーブル新設）
    │   └── backfill_title_and_tags.py           … T3（既存JSONからの補完バッチ、2段階処理）
    └── tests/
        ├── test_qa_repository.py
        ├── test_search_service.py
        └── test_tools.py
```

## 4. DBスキーマ移行指示（Phase 1 / T2, T3）

### 4.1 マイグレーションSQL（`migrations/0001_add_title_and_tag_tables.sql`）

```sql
ALTER TABLE qa_original
    ADD COLUMN IF NOT EXISTS title TEXT;

CREATE TABLE IF NOT EXISTS tag (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_tag_id INTEGER REFERENCES tag(id)
);

CREATE TABLE IF NOT EXISTS qa_tag (
    qa_id TEXT NOT NULL REFERENCES qa_original(uuid),
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    PRIMARY KEY (qa_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_qa_tag_tag_id ON qa_tag (tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_parent_tag_id ON tag (parent_tag_id);
```

（ADR-0005: タグは配列カラムではなく `tag`/`qa_tag` の関連テーブルで表現する。`parent_tag_id` は将来のツリー構造対応のための列で、MVP時点では全レコード `NULL` のまま投入する。）

### 4.2 実施上の注意（重要）

- `db_nomic/init.sql` は **PostgreSQLコンテナの初回起動時（データディレクトリが空の場合）のみ実行される**。既存の `db_nomic/data` には投入済みデータがあるため、`init.sql` を書き換えるだけでは既存環境には反映されない。
- そのため、以下の2系統の対応が必要:
  1. `db_nomic/init.sql` 自体にも `title` カラム定義・`tag`/`qa_tag` テーブル定義を追記し、**今後新規に環境構築する場合**に反映されるようにする。
  2. **既存の稼働中DBに対しては** `migrations/0001_add_title_and_tag_tables.sql` を `docker compose exec db psql -U postgres -d chatbot -f /path/to/0001_add_title_and_tag_tables.sql` 等の方法で個別に適用する。

### 4.3 既存データの補完（T3）

`migrations/backfill_title_and_tags.py` にて、`data/exportjson_withguid.json` を読み込み、以下の2段階でデータを投入するバッチを用意する。

1. **titleの補完**: 各レコードの `guid` を `qa_original.uuid` に突き合わせて `title` を `UPDATE` する。
2. **タグの投入（2段階）**:
   1. 全レコードから重複を除いたユニークなタグ名を抽出し、`tag` テーブルへ `INSERT ... ON CONFLICT (name) DO NOTHING` で投入する（`parent_tag_id` は `NULL` のまま）。
   2. 各QAレコードの `guid` とタグ名から `tag.id` を引き当て、`qa_tag(qa_id, tag_id)` へ `INSERT ... ON CONFLICT DO NOTHING` で投入する。

- 既存 `seed_helpers.py` の読み込みロジック（JSONパース部分）を参考にすること。
- 冪等性を担保すること（何度実行しても同じ結果になるようにする。`ON CONFLICT DO NOTHING` を活用）。

## 5. インターフェース仕様（確定版）

### 5.1 `Document` モデル（`models/document.py` に定義するシグネチャ）

```python
@dataclass
class Document:
    id: str
    source_type: str        # "qa" 固定（MVP時点）
    title: str
    content: str
    score: float             # 0.0〜1.0
    metadata: dict           # {"tags": list[str], "category": str, "guid": str}
```

### 5.2 `Repository` 抽象基底クラス（`repository/base.py`）

```python
class Repository(ABC):
    @abstractmethod
    def search(
        self,
        query: str,
        tags: list[str] | None = None,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[Document]:
        ...
```

### 5.3 `QARepository`（`repository/qa_repository.py`）

- コンストラクタで DB接続・embedding呼び出し関数（既存 `app/src/embedding.get_embedding` と同等のもの）を受け取る（DI）。
- `search()` 内部手順:
  1. `query` を embedding API でベクトル化する。
  2. 既存 `search_similar` 相当のSQL（`question_altered` ⋈ `qa_original`、`embedding <=>` でソート）に加え、`qa_tag` ⋈ `tag` を結合してタグ名を取得する（`array_agg(tag.name)` 等で1行に集約する）。`tags` が指定されている場合は `EXISTS`句や`HAVING`句でタグ名との一致条件を追加し、`category` が指定されている場合は `category_id = (SELECT id FROM category WHERE name = %s)` を追加する。タグの階層（`parent_tag_id`）を辿った祖先/子孫展開はMVPでは行わず、指定タグ名との完全一致のみとする（ADR-0005）。
  3. 取得した各行を `Document` に変換する（0.0節の変換表参照。`metadata.tags` は集約したタグ名一覧）。
  4. `distance` を 0.1節のスコア変換式でスコア化する。

### 5.4 `SearchService`（`services/search_service.py`）

```python
class SearchService:
    def __init__(self, repositories: list[Repository]):
        self.repositories = repositories

    def search(
        self,
        query: str,
        tags: list[str] | None = None,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[Document]:
        # 各Repositoryの結果を集約し、score降順でtop_k件に整形して返す
        ...
```

- MVPでは `repositories` は `QARepository` のみが渡される想定だが、複数repositoryを渡しても動作するように実装すること（将来のPDF/Manual追加を見据える）。

### 5.5 `search_knowledge` MCPツール 入出力（JSON Schema）

**入力スキーマ**

```json
{
  "type": "object",
  "properties": {
    "query": { "type": "string" },
    "top_k": { "type": "integer", "default": 5, "minimum": 1 },
    "tags": { "type": "array", "items": { "type": "string" } },
    "category": { "type": "string" },
    "min_score": { "type": "number", "default": 0.0 }
  },
  "required": ["query"]
}
```

**出力スキーマ**

```json
{
  "type": "object",
  "properties": {
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "source_type": { "type": "string" },
          "title": { "type": "string" },
          "content": { "type": "string" },
          "score": { "type": "number" },
          "metadata": { "type": "object" }
        },
        "required": ["id", "source_type", "title", "content", "score", "metadata"]
      }
    }
  },
  "required": ["results"]
}
```

### 5.6 タグ管理MCPツール（ADR-0006）

`TagRepository`（`repository/tag_repository.py`）は、コンストラクタでDB接続を受け取り、以下のメソッド群を提供する。**内部状態としてタグ情報をキャッシュしてはならない**（呼び出しの都度SQLでDBを参照すること。外部からの直接変更を即座に反映するため）。

```python
class TagRepository:
    def list_tags(self, parent_tag_id: int | None = None) -> list[TagNode]:
        ...

    def create_tag(self, name: str, parent_tag_id: int | None = None) -> TagNode:
        ...

    def rename_tag(self, tag_id: int, new_name: str) -> TagNode:
        ...

    def move_tag(self, tag_id: int, new_parent_tag_id: int | None) -> TagNode:
        ...

    def delete_tag(self, tag_id: int) -> None:
        ...
```

`TagNode` は `{id, name, parent_tag_id, children: list[TagNode]}` のような構造を想定する（`list_tags`が木構造で返す場合）。

**循環参照防止（T18）**: `create_tag`（`parent_tag_id`指定時）および`move_tag`では、指定された`new_parent_tag_id`が対象タグ自身、またはその子孫タグでないことを検証する。検証方法の例:

1. `new_parent_tag_id` から `parent_tag_id` を再帰的に辿り、対象タグの `tag_id` に到達しないことを確認する（再帰CTEまたはアプリケーション側でのループ処理）。
2. 到達する場合は「循環参照になるため許可しない」エラーを返す。

**`delete_tag`の挙動**: 以下のいずれかに該当する場合はデフォルトで削除を拒否し、エラーを返す。

- `qa_tag` に当該 `tag_id` を参照する行が存在する
- `tag.parent_tag_id` に当該 `tag_id` を指定している子タグが存在する

**MCPツール入出力（例）**

```json
// create_tag 入力
{ "name": "積算システムの操作方法", "parent_tag_id": 3 }

// create_tag 出力
{ "id": 12, "name": "積算システムの操作方法", "parent_tag_id": 3 }
```

```json
// list_tags 出力（木構造の例）
{
  "tags": [
    {
      "id": 3, "name": "積算システム", "parent_tag_id": null,
      "children": [
        { "id": 12, "name": "積算システムの操作方法", "parent_tag_id": 3, "children": [] }
      ]
    }
  ]
}
```

各ツールのエラーレスポンス（循環参照エラー、参照制約違反エラー、タグ名重複エラー等）の形式は、5.5節の`search_knowledge`と同様にMCPエラーレスポンスの規約に従うこと。

## 6. 設定・環境変数一覧（確定表）

| 変数名 | 例 | 用途 |
|---|---|---|
| KNOWLEDGE_MCP_PORT | 8100 | Knowledge MCPサーバの待受ポート |
| DATABASE_URL | postgresql://postgres:postgres@db:5432/chatbot | 既存chatbot_dbへの接続（既存appと共有） |
| LMSTUDIO_EMBEDDING_URL | ${LMSTUDIO_EMBEDDING_URL}（既存と共有） | クエリのベクトル化 |
| MODEL_EMBEDDING | ${MODEL_EMBEDDING}（既存と共有） | embeddingモデル名 |
| KNOWLEDGE_MCP_DEFAULT_TOP_K | 5 | search_knowledgeのデフォルトtop_k |

`.env.example` に上記を追記すること。

## 7. `docker-compose.yml` 変更指示（差分）

```yaml
  knowledge_mcp:
    build: ./knowledge_mcp
    container_name: chatbot_knowledge_mcp
    ports:
      - "${KNOWLEDGE_MCP_PORT:-8100}:8100"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/chatbot
      - LMSTUDIO_EMBEDDING_URL=${LMSTUDIO_EMBEDDING_URL}
      - MODEL_EMBEDDING=${MODEL_EMBEDDING}
      - KNOWLEDGE_MCP_DEFAULT_TOP_K=${KNOWLEDGE_MCP_DEFAULT_TOP_K:-5}
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8100/health"]
      interval: 5s
      timeout: 5s
      retries: 20
```

- 既存 `app` / `frontend` / `db` / `conversation_db` サービス定義には変更を加えない。
- `README.md` の「利用前に」節へ、Knowledge MCPサーバ起動に関する手順を追記すること（Phase 6完了後）。

## 8. 実装順序と依存関係（再掲・詳細化）

1. T1（雛形） → T2・T3（DB移行、既存appには影響しないことを確認しながら実施） → T4・T5（モデル/抽象） → T6（QARepository、必ずT2完了後） → T7（SearchService） → T8・T9・T10（MCP層、必ずT7完了後） → T11・T12（Docker統合） → T13〜T15（検証）。
2. T2・T3 は既存 `chatbot_db` を直接変更するため、既存appの動作確認（`data/eval_queries.csv` によるMRR測定等）をT2適用前後で実施し、既存機能に影響がないことを確認してから先へ進むこと。

## 9. テスト・検証指示（Phase 6）

### 9.1 単体テスト観点

- `QARepository.search`: tags/categoryフィルタの有無による結果差分、スコア変換式の境界値（distance=0, distance大）。
- `SearchService.search`: 複数Repositoryを渡した場合の集約・top_k切り詰めの正しさ（モックRepositoryを用いる）。
- `search_knowledge`ツール: 入力スキーマのバリデーション（`query`必須、`top_k`型不正時のエラー）。

### 9.2 精度検証（既存評価との比較）

- 既存 `app` の `evaluate`（`python -m main.evaluate --top-k 10 --output /tmp/results.csv`）で得られるMRRを基準値とする。
- Knowledge MCP経由（`search_knowledge`呼び出し）で同じ `data/eval_queries.csv` を用いたMRRを算出し、基準値と同等以上であることを確認する。
- 差分が生じた場合は、スコア変換式・SQL条件（フィルタ有無）の差異を切り分けて報告する。

### 9.3 手動疎通確認

- MCPインスペクタ等の汎用MCPクライアントツールから `search_knowledge` を呼び出し、6.4の入出力仕様通りのレスポンスが返ることを確認する。
- `tags` / `category` を指定した場合、指定しない場合の両方で確認する。

### 9.4 タグ管理ツールのテスト観点（T19）

- `create_tag`: 親タグ指定あり/なしの両方で正しく作成されること。同名タグの重複作成がエラーになること（`tag.name`のUNIQUE制約）。
- `move_tag` / `create_tag`: 循環参照になる操作（例: 自分自身を親に指定、自分の子孫を親に指定）が拒否されること。
- `delete_tag`: `qa_tag`から参照されているタグ、子タグを持つタグの削除がデフォルトで拒否されること。参照のないタグは削除できること。
- `list_tags`: 木構造が正しく組み立てられること（複数階層のケースを含む）。
- **重要**: `tag`テーブルをSQL等で直接変更した直後に `list_tags` を呼び出し、キャッシュされた古い情報ではなく最新の内容が返ることを確認する（ADR-0006のキャッシュしない設計の検証）。

## 10. 完了条件（要件定義書11章のDoDに対応する実装レベルの確認項目）

- [ ] マイグレーション適用後も既存app（`chatbot_app`）が無変更で正常動作する。
- [ ] `search_knowledge` がMCPクライアントから呼び出せる（9.3）。
- [ ] MRRが既存 `search_similar` 経由と同等以上（9.2）。
- [ ] `metadata` に `title`/`tags`/`category`/`guid` が正しく含まれる。
- [ ] `tags`/`category`フィルタが機能する。
- [ ] `docker-compose up` で `knowledge_mcp` サービスが正常起動し、ヘルスチェックが通る。
- [ ] `SearchService`・`search_knowledge` の変更なしに `Repository` を追加できることを、ダミーRepositoryを用いた結合テストで確認する。
- [ ] `list_tags`/`create_tag`/`rename_tag`/`move_tag`/`delete_tag` が仕様通りに動作し、循環参照・参照制約違反が適切に拒否される（9.4）。
- [ ] `tag`テーブルを外部から直接変更した場合でも、Knowledge MCP側の再起動なしに `list_tags` 等へ反映される（キャッシュしない設計の確認）。

## 11. 実装時の注意点・落とし穴

- embeddingの次元数（768, `nomic-embed-text-v1.5`相当）を前提にしたコードにしないこと。将来モデルを差し替える可能性があるため、次元数は設定値として扱う。
- `db_nomic/init.sql` を直接書き換えても既存の稼働中DBには反映されない（4.2節）。この点を見落として「マイグレーションしたつもりが反映されていない」という事故が起きやすいので注意。
- 既存 `app/src/db.py` の `search_similar` はそのまま残し、変更・削除しないこと（要件定義書10章、並行運用前提）。
- `qa_tag`/`tag` との結合が増える分、既存 `search_similar` よりクエリコストが上がる。`qa_tag.tag_id` へのインデックス（4.1節）を必ず作成し、必要に応じて実行計画を確認すること。
- `parent_tag_id` はMVP時点では全件 `NULL` で投入し、階層を用いた検索ロジックは実装しないこと（実装するとADR-0005のスコープを超える）。将来対応する場合は別途設計・ADR更新が必要。
- `KNOWLEDGE_MCP_PORT` をホストに公開する場合、社内ネットワーク外からアクセス可能にならないよう、Docker/ネットワーク設定を確認すること（0節の認証方針を参照）。
- `TagRepository`（および他の箇所でタグ情報を扱うコード）は、プロセス内でのメモリキャッシュ・グローバル変数への保持を行わないこと。外部から `tag` テーブルが直接変更された場合に反映漏れが起きる（ADR-0006）。
- タグ管理ツール（`create_tag`等）は書き込み系であり、`search_knowledge`と異なりリクエストの正当性検証（誰が呼んでいるか）が今後必要になる可能性が高い。認証方式が未確定（Open Issue #4, #10）のまま安易に外部公開しないこと。

## 12. 実装着手前に確認をお願いしたい事項（再掲）

本書 0節の内容（tagsの関連テーブル化、タグ管理機能の提供方式を含む）、および**タグの階層検索を今回のMVPでは実装しない（完全一致のみとする）方針**は、いずれも発注者により承認済みであり、実装着手可能な状態にある。

残る主な検討事項:

- **タグ書き込み系ツールのアクセス制御**（Open Issue #10）。
- **タグ管理機能の責務分離の見直し**（将来、別MCPサーバへ切り出すか、Open Issue #11）。
