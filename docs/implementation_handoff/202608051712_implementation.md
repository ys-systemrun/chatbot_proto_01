# タグ選択（Tag Selector）MCP サーバ 実装指示書

- 文書番号: IMPL-202608051712
- 対象プロジェクト: chatbot_invitro / Tag Selector MCP サーバ
- 参照文書:
  - 要件定義書 `docs/requirement/202608051636.md`（REQ-202608051636）
  - ADR `docs/adr/0007〜0012`
  - 関連（既存）: Knowledge MCP サーバ 要件定義書 `docs/requirement/202608041002.md`、ADR-0001〜0006、実装指示書 `docs/implementation_handoff/202608041013_implementation.md`
- 本書の位置づけ: 要件定義書・ADRで確定した方針を、実装担当者（開発者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。本書自体はソースコードを含まない（インターフェース仕様・作業手順・設定値の指示にとどめる）。実装は別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確定した事項

要件定義書の Open Issues のうち、実装着手には確定が必要だが未決だった項目について、以下の通り値を定めた。**本節の内容は発注者により承認済み。**

| 項目 | 決定内容 | 理由・備考 |
|---|---|---|
| タグ知識ベースの正本（ADR-0008） | `taxonomy.yaml`等は採用せず、既存 `tag` テーブル（+ 新設 `tag_alias` テーブル）を正本とする | Knowledge MCP側の`tag`テーブルとの二重管理・同期ズレを避けるため |
| MVPのタグ選択アルゴリズム（ADR-0009） | Embedding層・階層探索は実装せず、Alias辞書によるルールベース処理 + LLMによる一段階選択とする | 現状タグ件数が少数・`parent_tag_id`が全件NULLのため |
| レスポンス形式（ADR-0010） | `select_tags`は`id`/`name`/`score`/`path`のみを返す。`weight`/`expand_children`を含むSearchPlan形式は採用しない | Knowledge MCP側が階層展開検索に未対応のため |
| タグ知識ベースのキャッシュ方針（ADR-0011） | 起動時ロード＋`reload_taxonomy`ツールによる明示的リロード＋定期ポーリング（`TAXONOMY_RELOAD_INTERVAL_SEC`） | Embedding層追加時の性能要件を見据え、Knowledge MCPの無キャッシュ方針(ADR-0006)とは別方針とする |
| LLM接続先（ADR-0012） | MVP時点はローカルLLM（LM Studio）を主たる接続先とする。`LLM_PROVIDER=lmstudio`をデフォルトとする | 発注者の指示により決定。Bedrock/OpenAIは`LLMClient`実装追加で対応 |
| Knowledge MCP側タグ管理ツール拡張の着手時期（要件定義書 Open Issue #1） | Tag Selector MCPのMVPが動作することを確認した後に着手する。MVP検証時点では`description`/`tag_alias`はDBへ直接投入する暫定運用とする | 発注者の指示により決定 |
| タグ選択の精度評価方法（要件定義書 Open Issue #3） | 精度評価用データセットの整備は暫定的に行わない。少数の手動テストクエリによる動作確認に留める | 発注者の指示により決定。将来、定量評価が必要になった時点で改めて整備を検討する |
| 認証方式（要件定義書 Open Issue #6） | 本フェーズでは追加認証を実装せず、Docker内部ネットワーク限定公開（ホスト側ポート公開は開発時のみ）で運用する | Knowledge MCPと同様の暫定方針。恒久対応ではなく、Open Issue #6として継続管理 |

## 1. 全体進行フェーズ

| Phase | 目的 | 主な成果物 | 前提 |
|---|---|---|---|
| Phase 0 | 事前準備 | 作業ブランチ、ディレクトリ雛形 | なし |
| Phase 1 | DBスキーマ移行・暫定シード | `tag.description`カラム追加、`tag_alias`テーブル新設、検証用の暫定シードデータ投入 | Phase 0 |
| Phase 2 | Tag Metadata Repository / Retrieval Engine | タグ知識ベースのメモリキャッシュ、Alias辞書照合ロジック | Phase 1 |
| Phase 3 | Inference Engine / LLMClient | LM Studio呼び出し、プロンプト構築、スコア抽出 | Phase 2 |
| Phase 4 | MCP Tool層 | `select_tags`/`list_taxonomy`/`reload_taxonomy` ツール定義・サーバ起動 | Phase 3 |
| Phase 5 | Docker統合 | `docker-compose.yml`追記、`.env`追記、Dockerfile | Phase 4 |
| Phase 6 | 検証・受け入れ | 手動疎通確認、DoDチェック | Phase 5 |

以降の各節は、この順序で実施することを前提に指示する。後続フェーズは前フェーズの成果物を前提とするため、順序を入れ替えないこと。

## 2. WBS（作業分解構成）

| No. | タスク | Phase | 参照 | 成果物 |
|---|---|---|---|---|
| T1 | `tag_selector_mcp/` ディレクトリ雛形作成（3節のディレクトリ構成通り） | 0 | ADR-0007 | ディレクトリ一式 |
| T2 | `tag` へ `description TEXT` カラム追加 ＋ `tag_alias` テーブル新設スクリプト作成 | 1 | 要件7.3, ADR-0008 | マイグレーションSQL |
| T3 | 検証用の暫定シードスクリプト作成（既存タグの一部にdescription/aliasを直接投入。0節「タグ管理ツール拡張の着手時期」を参照し、Knowledge MCPツール経由ではなくDB直接投入で行う） | 1 | 要件6.6, 13章Open Issue#1 | 暫定シードスクリプト（1回限り、繰り返し実行可能な冪等設計） |
| T4 | `TagMetadataRepository` 実装指示（起動時ロード・`reload`メソッド） | 2 | 要件6.2, ADR-0011 | `infrastructure/repository/tag_metadata_repository.py` 相当のシグネチャ |
| T5 | `RetrievalEngine` 実装指示（Alias辞書照合） | 2 | 要件6.3, ADR-0009 | `application/retrieval_engine.py` 相当のシグネチャ |
| T6 | `LLMClient` 抽象 + `LMStudioLLMClient` 実装指示 | 3 | ADR-0012 | `infrastructure/llm/base.py`, `infrastructure/llm/lmstudio.py` 相当のシグネチャ |
| T7 | `InferenceEngine` 実装指示（プロンプト構築・LLM呼び出し・スコア抽出） | 3 | 要件6.4 | `application/inference_engine.py` 相当のシグネチャ |
| T8 | `SelectTagsUseCase` 実装指示（Retrieval→Inferenceの束ね） | 3 | 要件6.1 | `application/select_tags.py` 相当のシグネチャ |
| T9 | `select_tags` MCPツール定義・入出力スキーマ実装指示 | 4 | 要件6.1 | `mcp/tools.py`, `mcp/schemas.py` 相当のシグネチャ |
| T10 | `list_taxonomy` / `reload_taxonomy` MCPツール定義実装指示 | 4 | 要件6.5, ADR-0011 | `mcp/tools.py`, `mcp/schemas.py` への追加分 |
| T11 | MCPサーバ起動エントリポイント実装指示（Streamable HTTP、定期ポーリングの起動を含む） | 4 | ADR-0007, ADR-0011 | `main.py` 相当のシグネチャ |
| T12 | ヘルスチェック手段の実装指示 | 4 | 要件8 | ヘルスチェックエンドポイント/リソース仕様 |
| T13 | `Dockerfile` 作成指示 | 5 | ADR-0007 | Dockerfile仕様 |
| T14 | `docker-compose.yml` / `.env.example` 追記指示 | 5 | 要件9 | 差分内容 |
| T15 | 手動疎通確認（サンプル質問でのテスト） | 6 | 要件11 | 確認結果 |
| T16 | DoDチェックリスト実施 | 6 | 要件11 | チェック結果 |

## 3. ディレクトリ・ファイル構成指示

```
chatbot_invitro/
└── tag_selector_mcp/
    ├── Dockerfile
    ├── pyproject.toml                … 依存関係定義（mcp SDK, psycopg2, requests 等）
    ├── src/
    │   └── tag_selector_mcp/
    │       ├── __init__.py
    │       ├── main.py               … エントリポイント。MCPサーバをStreamable HTTPで起動（T11）。起動時にTagMetadataRepository.load()と定期ポーリングタスクを開始する
    │       ├── mcp/
    │       │   ├── server.py         … MCPサーバインスタンス生成・ツール登録
    │       │   ├── tools.py          … select_tags/list_taxonomy/reload_taxonomyツールのハンドラ定義（T9, T10）
    │       │   └── schemas.py        … 入出力のJSON Schema／型定義（T9, T10）
    │       ├── application/
    │       │   ├── retrieval_engine.py   … RetrievalEngine実装（T5）
    │       │   ├── inference_engine.py   … InferenceEngine実装（T7）
    │       │   └── select_tags.py        … SelectTagsUseCase実装（T8）
    │       ├── infrastructure/
    │       │   ├── llm/
    │       │   │   ├── base.py       … LLMClient抽象基底クラス（T6）
    │       │   │   └── lmstudio.py   … LMStudioLLMClient実装（T6）
    │       │   └── repository/
    │       │       └── tag_metadata_repository.py  … タグ知識ベースのメモリキャッシュ実装（T4）
    │       ├── models/
    │       │   └── tag.py            … TagRecord / SelectedTag データモデル
    │       └── db/
    │           └── connection.py     … 既存chatbot_dbへの接続（既存app/src/db.pyのDB接続部分に準拠）
    ├── migrations/
    │   ├── 0001_add_tag_description_and_alias.sql   … T2
    │   └── seed_description_and_aliases.py           … T3（暫定シード、冪等設計）
    └── tests/
        ├── test_tag_metadata_repository.py
        ├── test_retrieval_engine.py
        ├── test_inference_engine.py
        └── test_tools.py
```

## 4. DBスキーマ移行指示（Phase 1 / T2, T3）

### 4.1 マイグレーションSQL（`migrations/0001_add_tag_description_and_alias.sql`）

```sql
ALTER TABLE tag
    ADD COLUMN IF NOT EXISTS description TEXT;

CREATE TABLE IF NOT EXISTS tag_alias (
    id SERIAL PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    alias TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_tag_alias_tag_id ON tag_alias (tag_id);
```

（ADR-0008: `description`は単一カラムとして`tag`に追加し、同義語は配列カラムではなく`tag_alias`関連テーブルで表現する。）

### 4.2 実施上の注意（重要）

- Knowledge MCPの実装指示書（`docs/implementation_handoff/202608041013_implementation.md` 4.2節）と同様、`db_nomic/init.sql` は**PostgreSQLコンテナの初回起動時（データディレクトリが空の場合）のみ実行される**。既存の稼働中DBには、本マイグレーションSQLを個別に適用する必要がある。
  1. `db_nomic/init.sql` 自体にも `tag.description` カラム定義・`tag_alias` テーブル定義を追記し、今後新規に環境構築する場合に反映されるようにする。
  2. 既存の稼働中DBに対しては `docker compose exec db psql -U postgres -d chatbot -f /path/to/0001_add_tag_description_and_alias.sql` 等の方法で個別に適用する。
- 本マイグレーションはKnowledge MCPが管理する`tag`テーブルへの列追加であるため、適用後にKnowledge MCP側の既存クエリ（`list_tags`等）が無変更で正常動作することを確認すること。

### 4.3 検証用の暫定シード（T3）

0節で確定したとおり、Knowledge MCP側のタグ管理ツール拡張は Tag Selector MCP のMVP動作確認後に着手する。そのため、MVP検証時点では `migrations/seed_description_and_aliases.py` にて、既存タグの一部（動作確認に必要な範囲でよい。例: 要件定義書に例示されている「積算システム」「積算システムの操作方法」等、数件〜十数件程度）に対し、DBへ直接以下を投入する。

1. `UPDATE tag SET description = %s WHERE id = %s` により、対象タグに説明文を設定する。
2. `INSERT INTO tag_alias (tag_id, alias) VALUES (%s, %s) ON CONFLICT (alias) DO NOTHING` により、同義語（例:「歩掛」→「積算」、「見積」→「積算」等）を登録する。

- 冪等性を担保すること（何度実行しても同じ結果になるようにする）。
- **このシードはあくまで動作確認用の暫定データであり、本番運用のタグ説明文・同義語の網羅的な整備ではない**ことをコメント等で明記すること。本番運用に向けた網羅的な整備は、Knowledge MCP側のツール拡張後に別途行う（要件定義書 Open Issue #2）。

## 5. インターフェース仕様（確定版）

### 5.1 `TagRecord` / `SelectedTag` モデル（`models/tag.py`）

```python
@dataclass
class TagRecord:
    id: int
    name: str
    description: str | None
    parent_tag_id: int | None
    aliases: list[str]           # tag_aliasから集約したalias一覧

@dataclass
class SelectedTag:
    id: int
    name: str
    score: float                  # 0.0〜1.0
    path: list[str]               # MVP時点は [name] のみ（ADR-0010）
```

### 5.2 `TagMetadataRepository`（`infrastructure/repository/tag_metadata_repository.py`）

```python
class TagMetadataRepository:
    def __init__(self, db_connection_factory, reload_interval_sec: int):
        ...

    def load(self) -> None:
        """tag ⋈ tag_alias を全件読み込み、内部キャッシュ（tag.id -> TagRecord の辞書等）を構築する。
        キャッシュの差し替えはアトミックに行うこと（新しい辞書を構築してから参照を切り替える。
        リクエスト処理中の参照と競合させないため）。"""
        ...

    def reload(self) -> None:
        """load()を再実行する。reload_taxonomyツールおよび定期ポーリングタスクから呼ばれる。"""
        ...

    def all_tags(self) -> list[TagRecord]:
        ...

    def find_tags_by_alias_match(self, query: str) -> list[TagRecord]:
        """queryに含まれる文字列とaliasesの一致（部分一致）を確認し、一致したTagRecordを返す。"""
        ...
```

- `parent_tag_id` はキャッシュのデータ構造としては保持するが、MVP時点でこれを用いた探索ロジックは実装しない（要件定義書4.2節）。
- `load()` / `reload()` は、DBアクセスに失敗した場合、既存のキャッシュを保持したままエラーをログに記録し、例外を呼び出し元（`reload_taxonomy`ツールハンドラ、または起動処理）へ伝播させること（キャッシュを空にして機能停止させない）。

### 5.3 `RetrievalEngine`（`application/retrieval_engine.py`）

```python
@dataclass
class RetrievalResult:
    confirmed: list[TagRecord]    # alias一致で確定したタグ
    candidates: list[TagRecord]   # Inference Engineへ渡す全タグ候補（MVPでは全件、ADR-0009）

class RetrievalEngine:
    def __init__(self, tag_repository: TagMetadataRepository):
        ...

    def retrieve(self, query: str) -> RetrievalResult:
        """
        1. tag_repository.find_tags_by_alias_match(query) の結果を confirmed とする。
        2. candidates は tag_repository.all_tags() の全件とする（Embeddingによる絞り込みは行わない）。
        """
        ...
```

### 5.4 `LLMClient` / `LMStudioLLMClient`（`infrastructure/llm/`）

```python
class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """promptを渡し、LLMの応答テキストをそのまま返す。"""
        ...

class LMStudioLLMClient(LLMClient):
    def __init__(self, base_url: str, model: str):
        ...

    def complete(self, prompt: str) -> str:
        """LM StudioのChat Completions API（OpenAI互換エンドポイント、例: POST {base_url}/v1/chat/completions）
        を呼び出し、応答メッセージ本文を返す。"""
        ...
```

- `LLM_PROVIDER` の値に応じて `LMStudioLLMClient` のインスタンスを生成する（MVPでは`lmstudio`のみ実装。`bedrock`/`openai`は将来追加、ADR-0012）。
- LM Studioへの接続失敗・タイムアウト時は、呼び出し元（`InferenceEngine`）へ例外を送出すること。

### 5.5 `InferenceEngine`（`application/inference_engine.py`）

```python
class InferenceEngine:
    def __init__(self, llm_client: LLMClient):
        ...

    def infer(
        self,
        query: str,
        retrieval_result: RetrievalResult,
        max_tags: int,
        confidence_threshold: float,
    ) -> list[SelectedTag]:
        """
        1. プロンプトを構築する（5.5.1節のテンプレート例を参照）。質問文、confirmed（alias一致で確定済みのタグ）、
           candidates（全タグのid・name・description）を含める。
        2. llm_client.complete(prompt) を呼び出す。
        3. LLM応答（JSON文字列を想定）をパースし、{tag_id, score} の一覧を得る。
        4. score が confidence_threshold 未満の要素を除外する。
        5. score降順で並べ替え、max_tags件に絞り込む。
        6. TagMetadataRepositoryから該当tagのnameを引き当て、SelectedTag(id, name, score, path=[name])のリストを返す。
        """
        ...
```

#### 5.5.1 プロンプトテンプレート例（`prompts/select_tags.md` 相当、詳細設計で最終確定）

```
あなたはタグ分類の専門家です。以下の質問に最も関連するタグを、与えられたタグ一覧の中から選んでください。

質問: {query}

タグ一覧:
{候補タグ each: "- id={id}, name={name}, description={description}"}

既に同義語辞書との一致により確定しているタグ: {confirmedのid・name一覧、なければ「なし」}

出力は以下のJSON形式のみとし、他の説明文は含めないでください。
{"selected": [{"tag_id": <id>, "score": <0.0から1.0の確信度>}, ...]}
```

- LLM応答がJSONとしてパースできない場合のフォールバック（空リストを返す、エラーログを記録する等）を実装すること（11章参照）。
- スコアの算出方法・正規化方式は、実際のLM Studioモデルでの応答傾向を見ながら詳細設計フェーズで調整すること（要件定義書6.4節）。

### 5.6 `SelectTagsUseCase`（`application/select_tags.py`）

```python
class SelectTagsUseCase:
    def __init__(self, retrieval_engine: RetrievalEngine, inference_engine: InferenceEngine):
        ...

    def execute(
        self,
        query: str,
        max_tags: int = 3,
        confidence_threshold: float = 0.0,
    ) -> list[SelectedTag]:
        retrieval_result = self.retrieval_engine.retrieve(query)
        return self.inference_engine.infer(query, retrieval_result, max_tags, confidence_threshold)
```

### 5.7 `select_tags` MCPツール 入出力（JSON Schema）

**入力スキーマ**

```json
{
  "type": "object",
  "properties": {
    "query": { "type": "string" },
    "max_tags": { "type": "integer", "default": 3, "minimum": 1 },
    "confidence_threshold": { "type": "number", "default": 0.0, "minimum": 0.0, "maximum": 1.0 }
  },
  "required": ["query"]
}
```

**出力スキーマ**

```json
{
  "type": "object",
  "properties": {
    "selected": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "integer" },
          "name": { "type": "string" },
          "score": { "type": "number" },
          "path": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["id", "name", "score", "path"]
      }
    }
  },
  "required": ["selected"]
}
```

### 5.8 `list_taxonomy` / `reload_taxonomy` MCPツール（ADR-0011）

```json
// list_taxonomy 出力（例）
{
  "tags": [
    { "id": 3, "name": "積算システム", "description": "積算システムに関する情報", "parent_tag_id": null, "aliases": ["積算"] },
    { "id": 12, "name": "積算システムの操作方法", "description": "積算システムの操作手順に関する情報", "parent_tag_id": 3, "aliases": ["操作方法", "使い方"] }
  ]
}
```

```json
// reload_taxonomy 入力: なし
// reload_taxonomy 出力（例）
{ "reloaded": true, "tag_count": 24 }
```

- `reload_taxonomy` 呼び出し時、`TagMetadataRepository.reload()` を呼び出し、リロード後のタグ件数を返す。DBアクセスに失敗した場合はMCPエラーレスポンスとして返し、既存キャッシュは維持する（5.2節）。
- 各ツールのエラーレスポンス形式は、Knowledge MCP実装指示書5.5節と同様にMCPエラーレスポンスの規約に従うこと。

## 6. 設定・環境変数一覧（確定表）

| 変数名 | 例 | 用途 |
|---|---|---|
| TAG_SELECTOR_MCP_PORT | 8200 | Tag Selector MCPサーバの待受ポート |
| DATABASE_URL | postgresql://postgres:postgres@db:5432/chatbot | 既存chatbot_dbへの接続（既存app・Knowledge MCPと共有） |
| LLM_PROVIDER | lmstudio | LLM実装の切り替え（MVPでは`lmstudio`のみ実装、ADR-0012） |
| LMSTUDIO_CHAT_URL | http://host.docker.internal:1234 | LM Studioのチャット補完APIのベースURL |
| LMSTUDIO_CHAT_MODEL | （LM Studioにロード済みのモデル名） | チャット補完に使用するモデル名 |
| TAXONOMY_RELOAD_INTERVAL_SEC | 300 | Tag Metadata Repositoryの自動リロード間隔（秒、ADR-0011） |
| TAG_SELECTOR_DEFAULT_MAX_TAGS | 3 | `select_tags`の`max_tags`デフォルト値 |
| TAG_SELECTOR_DEFAULT_CONFIDENCE_THRESHOLD | 0.0 | `select_tags`の`confidence_threshold`デフォルト値 |

`.env.example` に上記を追記すること。

## 7. `docker-compose.yml` 変更指示（差分）

```yaml
  tag_selector_mcp:
    build: ./tag_selector_mcp
    container_name: chatbot_tag_selector_mcp
    ports:
      - "${TAG_SELECTOR_MCP_PORT:-8200}:8200"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/chatbot
      - LLM_PROVIDER=${LLM_PROVIDER:-lmstudio}
      - LMSTUDIO_CHAT_URL=${LMSTUDIO_CHAT_URL}
      - LMSTUDIO_CHAT_MODEL=${LMSTUDIO_CHAT_MODEL}
      - TAXONOMY_RELOAD_INTERVAL_SEC=${TAXONOMY_RELOAD_INTERVAL_SEC:-300}
      - TAG_SELECTOR_DEFAULT_MAX_TAGS=${TAG_SELECTOR_DEFAULT_MAX_TAGS:-3}
      - TAG_SELECTOR_DEFAULT_CONFIDENCE_THRESHOLD=${TAG_SELECTOR_DEFAULT_CONFIDENCE_THRESHOLD:-0.0}
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8200/health"]
      interval: 5s
      timeout: 5s
      retries: 20
```

- 既存 `app` / `frontend` / `db` / `conversation_db` / `knowledge_mcp` サービス定義には変更を加えない。
- 認証は0節の決定どおり実装しない。ホスト側への `ports` 公開は開発時のみとし、社内ネットワーク外に公開しないよう運用上の注意をREADMEに明記すること。
- `README.md` の「利用前に」節へ、Tag Selector MCPサーバ起動に関する手順を追記すること（Phase 6完了後）。

## 8. 実装順序と依存関係（再掲・詳細化）

1. T1（雛形） → T2・T3（DB移行・暫定シード、Knowledge MCP側の既存動作に影響しないことを確認しながら実施） → T4・T5（Tag Metadata Repository / Retrieval Engine） → T6・T7（LLMClient / Inference Engine、必ずT4・T5完了後） → T8（SelectTagsUseCase） → T9・T10・T11・T12（MCP層、必ずT8完了後） → T13・T14（Docker統合） → T15・T16（検証）。
2. T2は既存Knowledge MCPが利用する`tag`テーブルへの列追加であるため、適用後にKnowledge MCP側（`list_tags`等）が無変更で正常動作することを確認してから先へ進むこと。

## 9. テスト・検証指示（Phase 6）

### 9.1 単体テスト観点

- `TagMetadataRepository.load`/`reload`: 正しくキャッシュが構築されること。DBに存在しない`parent_tag_id`参照等の異常系でも例外にならず適切にハンドリングされること。
- `RetrievalEngine.retrieve`: alias一致・不一致のケースで`confirmed`が正しく決まること。`candidates`が常に全タグを含むこと（MVP、ADR-0009）。
- `InferenceEngine.infer`: モック`LLMClient`を用い、`confidence_threshold`未満の除外、`max_tags`件への絞り込みが正しく行われること。LLM応答がJSONとしてパースできない場合に例外にならず、フォールバック処理（空リスト返却等）が動作すること。
- `select_tags`ツール: 入力スキーマのバリデーション（`query`必須、`max_tags`/`confidence_threshold`の型・範囲不正時のエラー）。

### 9.2 手動疎通確認（精度評価用データセットは整備しない、Open Issue #3解消）

- MCPインスペクタ等の汎用MCPクライアントツールから `select_tags` を呼び出し、5.7節の入出力仕様通りのレスポンスが返ることを確認する。
- 確認に用いるサンプル質問の例（4.3節で投入した暫定シードに対応させること）:
  - 「積算システムの使い方を教えてください」→ alias「使い方」経由で「積算システムの操作方法」等が確定・選択されることを確認する。
  - 「歩掛について教えてください」→ alias「歩掛」経由で「積算」等が確定・選択されることを確認する。
  - Alias辞書に一致しない質問文でも、Inference Engineの判定によりそれらしいタグが返ることを確認する。
- `reload_taxonomy`呼び出し前後で、DBを直接`UPDATE`/`INSERT`した`tag.description`/`tag_alias`の変更が反映されることを確認する。
- `TAXONOMY_RELOAD_INTERVAL_SEC`経過後、明示的な`reload_taxonomy`呼び出しなしに変更が反映されることを確認する（時間を短縮したテスト用設定値で確認してよい）。

## 10. 完了条件（要件定義書11章のDoDに対応する実装レベルの確認項目）

- [ ] マイグレーション適用後もKnowledge MCP（`list_tags`等）・既存appが無変更で正常動作する。
- [ ] `select_tags` がMCPクライアントから呼び出せる（9.2）。
- [ ] Alias辞書に登録した同義語を含む質問に対し、対応するタグが確定・優先される（9.2）。
- [ ] レスポンスの`selected`に`id`/`name`/`score`/`path`が正しく含まれる。
- [ ] `max_tags`/`confidence_threshold`によるフィルタが機能する（9.1）。
- [ ] `reload_taxonomy`呼び出し後、および定期ポーリング経過後に、DBを直接更新した`tag`/`tag_alias`の内容が反映される（9.2）。
- [ ] `docker-compose up`で`tag_selector_mcp`サービスが正常起動し、ヘルスチェックが通る。
- [ ] 将来Embedding層・階層探索を追加する際に`RetrievalEngine`以降のインターフェース変更が不要であることを設計レビューで確認する。
- [ ] 精度評価用データセットによる定量評価は本MVPでは実施しない（Open Issue #3解消）。

## 11. 実装時の注意点・落とし穴

- LM StudioのChat Completions APIはモデルによって出力形式が安定しない場合がある。5.5節のプロンプトで厳密なJSON出力を指示しても、余分なテキストが混入する等の応答が返る可能性があるため、パース失敗時のフォールバック処理（空リストを返す、リトライする等）を必ず実装すること。
- `TagMetadataRepository`のキャッシュ差し替えは、新しいデータ構造を構築してから参照を切り替える方式とし、リロード中の`select_tags`呼び出しが不整合な状態（一部だけ更新された状態）を参照しないようにすること。
- `description`/`tag_alias`がNULL・未登録のタグが多い間（4.3節の暫定シード以外）も、`RetrievalEngine`・`InferenceEngine`が例外を起こさず動作するようにすること（NULL/空文字列を許容する実装とする）。
- 認証を実装しない状態（0節の決定）でホスト側にポート公開する場合、社内ネットワーク外からアクセス可能にならないよう、Docker/ネットワーク設定を確認すること（Knowledge MCP実装指示書と同様の注意点）。
- `tag`テーブルへの`description`列追加はKnowledge MCPと共有するテーブルへの変更である。マイグレーション適用前後でKnowledge MCP側の`search_knowledge`・`list_tags`等の動作に影響がないことを必ず確認すること。
- 4.3節の暫定シードデータは、Knowledge MCP側のタグ管理ツール拡張が完了した後、正式な経路（`create_tag`/`rename_tag`等の拡張版）で登録し直す運用に切り替える前提であることをコード中のコメント等で明記し、実装担当者間で認識をそろえること。

## 12. 実装着手前に確認をお願いしたい事項（再掲）

本書 0節の内容（タグ知識ベースの正本、MVPのタグ選択アルゴリズム、レスポンス形式、キャッシュ方針、LLM接続先、タグ管理ツール拡張の着手時期、精度評価方法、認証方式）は、いずれも発注者により確認・承認済みであり、実装着手可能な状態にある。

残る主な検討事項（要件定義書13章 Open Issue、実装には支障がないため並行して整理してよい）:

- **既存タグへのdescription/aliasの初期投入範囲**（Open Issue #2）: 4.3節の暫定シードはあくまで動作確認用の最小限のデータであり、本番運用に向けた網羅的な整備の範囲・時期は別途整理が必要。
- **タグ件数の将来見込み**（Open Issue #5）: Embedding層の追加要否を再検討するタイミングの目安値。
- **`reload_taxonomy`の自動ポーリング間隔の最終値**（Open Issue #8）: 6章では暫定値300秒としているが、運用開始後の実測に基づき見直すこと。
- **将来のSearchPlan形式への移行方針**（Open Issue #9）: Knowledge MCP側の階層展開検索実装状況に応じて別途設計変更が必要。
