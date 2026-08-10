# QAデータ・タグ管理UI（front_dev / web_backend 拡張）実装指示書

- 文書番号: IMPL-202608060837
- 対象プロジェクト: chatbot_invitro / front_dev, web_backend, Knowledge MCP サーバ（既存拡張）
- 参照文書:
  - 要件定義書 `docs/requirement/202608060826.md`（REQ-202608060826）
  - ADR `docs/adr/0013〜0015`（本機能）、ADR-0005・0006・0008（前提となる既存決定）
  - 既存実装（変更対象）: `front_dev/src/`, `web_backend/main/`, `web_backend/src/`, `knowledge_mcp/src/knowledge_mcp/`
  - 既存実装指示書（参考）: `docs/implementation_handoff/202608041013_implementation.md`, `docs/implementation_handoff/202608051712_implementation.md`
- 本書の位置づけ: 要件定義書・ADRで確定した方針を、実装担当者（開発者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。本書自体はソースコードを含まない（インターフェース仕様・作業手順・設定値の指示にとどめる）。実装は別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確定した事項

要件定義書の Open Issues のうち、実装着手には確定が必要だが未決だった項目について、以下の通り値を定めた。**本節の内容は発注者により承認済み。**

| 項目 | 決定内容 | 理由・備考 |
|---|---|---|
| QA・タグの削除機能（Open Issue #1） | QAデータの削除は本フェーズでは実装しない。タグの削除は既存 `delete_tag` の挙動（`qa_tag`参照・子タグ存在時は拒否）をそのまま踏襲する | 影響範囲の精査が完了していないため。Open Issue #1として継続管理 |
| 書き込み系APIのアクセス制御（Open Issue #2） | 本フェーズでは追加認証を実装せず、既存Knowledge MCP/Tag Selector MCPと同様、社内ネットワーク限定公開で運用する | 恒久対応ではない。Open Issue #2として継続管理 |
| `question_altered`の個別編集（Open Issue #3） | 本フェーズでは対応しない。`create_qa`は`question_text`と同一内容の`question_altered`行を1件のみ生成し、`update_qa`はその1件のみを再計算する | 要件定義書6.3節・6.5節の通り |
| web_backendのMCPクライアント実装方式（Open Issue #4） | リクエスト（HTTPハンドラ呼び出し）ごとにMCPクライアントセッションを新規に張り、処理完了後にクローズする方式とする。コネクションプール的な維持は行わない | 実装をシンプルにし、まず正しく動くことを優先する。同時アクセス数が少数（要件定義書8章）であるため性能上の懸念は小さいと判断。将来的な最適化はOpen Issueとして継続 |
| カテゴリの登録・編集（Open Issue #5） | 本フェーズでは実装しない。`list_categories`による参照のみ提供する | 要件定義書4.2節の通り |
| タグ削除時の`tag_alias`の扱い（Open Issue #6） | `delete_tag`実行時、当該タグの`qa_tag`参照・子タグの存在チェックを通過した場合、紐づく`tag_alias`行は`delete_tag`内でカスケード削除する（別ツールでの事前削除は不要とする） | 利用者が`tag_alias`の存在を意識せずタグを削除できるようにするため。`tag`自体の削除同様、`qa_tag`参照・子タグ存在時は拒否する制約が先に効くため、danglingな`tag_alias`が残るリスクはない |
| `list_qa`のページング方式 | `limit`/`offset`方式。デフォルト `limit=20`、上限 `limit<=100` | シンプルさを優先。カーソル方式は本フェーズでは採用しない |
| 操作ログ | 操作者の記録は行わず、操作種別（作成/更新/削除）・対象ID・変更内容・タイムスタンプのみを既存 `web_backend/src/log` 相当の方式でログ出力する | 認証方式未確定のため操作者を記録できない（要件定義書8章） |
| front_devのルーティング（ADR-0015） | `/admin`配下のみ`react-router-dom`を導入する。既存3画面（`App`/`AppStateless`/`AppEvaluatedMessages`）とその分岐方式は変更しない | ADR-0015の通り |

## 1. 全体進行フェーズ

| Phase | 目的 | 主な成果物 | 前提 |
|---|---|---|---|
| Phase 0 | 事前準備 | 作業ブランチ | なし |
| Phase 1 | Knowledge MCP: QA管理ツールの追加 | `list_qa`/`get_qa`/`create_qa`/`update_qa`/`list_categories` | Phase 0 |
| Phase 2 | Knowledge MCP: タグ管理ツールのdescription/alias対応拡張 | `create_tag`/`rename_tag`拡張、`set_tag_description`/`add_tag_alias`/`remove_tag_alias`、`list_tags`出力拡張 | Phase 0（Phase 1と並行可） |
| Phase 3 | web_backend: MCPクライアント・BFF API | `/api/qa/*`, `/api/tags/*`, `/api/categories` | Phase 1, Phase 2 |
| Phase 4 | front_dev: 管理画面ルーティング・ページ実装 | `AppAdmin`、QA一覧/編集ページ、タグ階層/編集ページ | Phase 3 |
| Phase 5 | Docker/環境変数統合 | `docker-compose.yml`, `.env.example`, `vite.config.ts` 差分 | Phase 3（Phase 4と並行可） |
| Phase 6 | 検証・受け入れ | 疎通確認、DoDチェック | Phase 4, Phase 5 |

以降の各節は、この順序で実施することを前提に指示する。Phase 1とPhase 2は互いに独立（同じKnowledge MCPリポジトリ内だが担当ファイルが異なる）のため並行実施してよいが、Phase 3はPhase 1・2の両方が完了してから着手すること。

## 2. WBS（作業分解構成）

### 2.1 Knowledge MCP（QA管理ツール, Phase 1）

| No. | タスク | 参照 | 成果物 |
|---|---|---|---|
| T1 | `QaManagementRepository` 実装指示（`qa_original`/`question_altered`/`qa_tag`へのCRUD、embedding計算） | 要件6.5, ADR-0014 | `repository/qa_management_repository.py` 相当のシグネチャ |
| T2 | `list_qa`/`get_qa` MCPツール定義・入出力スキーマ実装指示 | 要件6.4, 6.5 | `mcp/tools.py`, `mcp/schemas.py` への追加分 |
| T3 | `create_qa`/`update_qa` MCPツール定義・入出力スキーマ実装指示（embedding再計算を含む） | 要件6.3, 6.5, ADR-0014 | `mcp/tools.py`, `mcp/schemas.py` への追加分 |
| T4 | `list_categories` MCPツール定義実装指示 | 要件6.5 | `mcp/tools.py`, `mcp/schemas.py` への追加分 |
| T5 | QA管理ツールの単体テスト観点整理・実装指示 | 要件11 | `tests/test_qa_management_repository.py`, `tests/test_tools.py` への追加分 |

### 2.2 Knowledge MCP（タグ管理ツール拡張, Phase 2）

| No. | タスク | 参照 | 成果物 |
|---|---|---|---|
| T6 | `TagRepository` 拡張実装指示（`description`更新、`tag_alias`のCRUD、`delete_tag`のcascade削除対応） | 要件6.6, ADR-0008 | `repository/tag_repository.py` の変更差分 |
| T7 | `create_tag`/`rename_tag`の`description`パラメータ対応、`set_tag_description`/`add_tag_alias`/`remove_tag_alias` MCPツール定義実装指示 | 要件6.6 | `mcp/tools.py`, `mcp/schemas.py` の変更差分 |
| T8 | `list_tags`出力への`description`/`aliases`追加実装指示、既存呼び出し元（`search_knowledge`のtagsフィルタ等）への影響確認 | 要件6.6 | `mcp/schemas.py` の変更差分、影響確認結果 |

### 2.3 web_backend（BFF, Phase 3)

| No. | タスク | 参照 | 成果物 |
|---|---|---|---|
| T9 | Knowledge MCP用MCPクライアントラッパー実装指示（接続先URL、ツール呼び出しの共通関数、エラーマッピング） | 要件6.4, ADR-0013 | `src/mcp_client/knowledge_mcp_client.py` 相当のシグネチャ |
| T10 | `/api/qa` 系エンドポイント実装指示（一覧・詳細・登録・編集） | 要件6.4 | `main/admin_qa.py` 相当のシグネチャ |
| T11 | `/api/tags` 系エンドポイント実装指示（一覧・登録・編集・削除） | 要件6.4 | `main/admin_tags.py` 相当のシグネチャ |
| T12 | `/api/categories` エンドポイント実装指示 | 要件6.4 | `main/admin_qa.py` への追加分（またはユーティリティモジュール） |
| T13 | 業務エラー（`TagError`/`QaError`相当）のHTTPステータスへのマッピング実装指示 | 要件6.4 | エラーハンドラ仕様 |
| T14 | FastAPIアプリへの新規ルータ登録・既存エンドポイントとの共存確認 | 要件10 | `main/main.py` または `main/main_stateless.py` への変更差分 |

### 2.4 front_dev（Phase 4）

| No. | タスク | 参照 | 成果物 |
|---|---|---|---|
| T15 | `react-router-dom` 導入・`AppAdmin` エントリポイント実装指示（ADR-0015） | ADR-0015 | `main.tsx` 変更差分、`AppAdmin.tsx` 相当のシグネチャ |
| T16 | `api.ts` への新規API呼び出し関数追加指示（QA・タグ・カテゴリ） | 要件6.4 | `api.ts` への追加分、型定義（`domain/admin/`） |
| T17 | QA一覧ページ実装指示（検索・絞り込み・ページング） | 要件6.1 | `feature/qa_admin/QaListPage.tsx` 相当のシグネチャ |
| T18 | QA登録・編集フォーム実装指示 | 要件6.3 | `feature/qa_admin/QaFormPage.tsx` 相当のシグネチャ |
| T19 | タグ階層ページ実装指示（ツリー表示、登録編集操作の統合） | 要件6.2 | `feature/tag_admin/TagTreePage.tsx` 相当のシグネチャ |
| T20 | タグピッカー共通コンポーネント実装指示（QA編集フォーム・タグ階層ページで共用） | 要件6.3 | `feature/tag_admin/TagPicker.tsx` 相当のシグネチャ |

### 2.5 Docker/環境変数・検証（Phase 5, 6）

| No. | タスク | 参照 | 成果物 |
|---|---|---|---|
| T21 | `docker-compose.yml`（`web_backend`サービス）変更指示 | 要件9.1 | 差分内容 |
| T22 | `.env.example` 追記指示 | 要件9.3 | 差分内容 |
| T23 | `vite.config.ts` プロキシ設定追記指示 | 要件9.2 | 差分内容 |
| T24 | 手動疎通確認（QA一覧/登録/編集、タグ階層/登録/編集の一連の操作） | 要件11 | 確認結果 |
| T25 | 既存機能への影響確認（`/ask`等チャット機能、既存`search_knowledge`/`list_tags`呼び出し） | 要件10 | 確認結果 |
| T26 | DoDチェックリスト実施 | 要件11 | チェック結果 |

## 3. ディレクトリ・ファイル構成指示（既存構成への追加差分）

### 3.1 Knowledge MCP（`knowledge_mcp/`）

```
knowledge_mcp/src/knowledge_mcp/
├── repository/
│   ├── tag_repository.py        … 既存。T6でdescription/tag_alias対応・delete_tagのcascade削除を追加
│   └── qa_management_repository.py  … 新規（T1）。qa_original/question_altered/qa_tagへのCRUD + embedding計算
├── mcp/
│   ├── tools.py                 … 既存。T2, T3, T4, T7で新規ツールのハンドラを追加登録
│   └── schemas.py               … 既存。T2, T3, T4, T7, T8でスキーマ追加・拡張
└── models/
    └── qa.py                    … 新規（T1）。QaDetail / QaSummary データモデル

knowledge_mcp/tests/
├── test_qa_management_repository.py   … 新規（T5）
└── test_tools.py                      … 既存。T5, T7, T8のテストケースを追加
```

### 3.2 web_backend（`web_backend/`）

```
web_backend/main/
├── main.py または main_stateless.py   … T14で新規ルータをインクルード（既存エンドポイントは変更しない）
├── admin_qa.py            … 新規（T10, T12）。/api/qa, /api/qa/{id}, /api/categories
└── admin_tags.py          … 新規（T11）。/api/tags, /api/tags/{id}

web_backend/src/
└── mcp_client/
    ├── __init__.py
    └── knowledge_mcp_client.py   … 新規（T9）。MCPクライアントの共通ラッパー、エラーマッピング（T13）
```

### 3.3 front_dev（`front_dev/`）

```
front_dev/src/
├── main.tsx                          … T15で/adminプレフィックスの分岐を追加
├── AppAdmin.tsx                      … 新規（T15）。react-router-domによる管理画面のルーティング定義
├── api.ts                            … T16で新規API呼び出し関数を追加
├── domain/
│   └── admin/
│       ├── qa.ts                     … 新規（T16）。QaSummary/QaDetail 等の型定義
│       └── tag.ts                    … 新規（T16）。TagNode 等の型定義（Knowledge MCPのTagNodeに対応）
└── feature/
    ├── qa_admin/
    │   ├── QaListPage.tsx            … 新規（T17）
    │   └── QaFormPage.tsx            … 新規（T18）
    └── tag_admin/
        ├── TagTreePage.tsx           … 新規（T19）
        └── TagPicker.tsx             … 新規（T20）。QaFormPage.tsxからも共用
```

`front_dev/package.json` の `dependencies` に `react-router-dom` を追加すること（T15）。

## 4. インターフェース仕様（確定版）

### 4.1 Knowledge MCP: `QaManagementRepository`（T1）

```python
@dataclass
class QaSummary:
    id: str
    title: str
    category: str | None
    tags: list[str]
    question_altered_count: int

@dataclass
class QaDetail:
    id: str
    title: str
    question_text: str
    answer_text: str
    category: dict | None   # {"id": int, "name": str}
    tags: list[dict]        # [{"id": int, "name": str}, ...]
    question_altered_count: int


class QaError(Exception):
    """QA登録編集の業務エラー（必須項目欠落、存在しないcategory_id/tag_ids指定等）。"""


class QaManagementRepository:
    def __init__(self, db: Database, embed_fn: Callable[[str], list[float]]):
        ...

    def list_qa(
        self,
        keyword: str | None = None,
        category: str | None = None,
        tag_ids: list[int] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[QaSummary], int]:
        """(件数分のQaSummary, 全体件数) を返す。"""
        ...

    def get_qa(self, qa_id: str) -> QaDetail:
        """存在しない場合はQaErrorを送出する。"""
        ...

    def create_qa(
        self,
        title: str,
        question_text: str,
        answer_text: str,
        category_id: int | None = None,
        tag_ids: list[int] | None = None,
    ) -> QaDetail:
        """
        1. uuid4()でqa_idを発行し、qa_originalへINSERTする。
        2. question_textをembed_fnでベクトル化し、question_altered(qa_id, text=question_text, embedding)を1件INSERTする。
        3. tag_idsが指定されている場合、qa_tagへ一括INSERTする（既存TagRepository同様、存在しないtag_idはQaErrorとする）。
        """
        ...

    def update_qa(
        self,
        qa_id: str,
        title: str | None = None,
        question_text: str | None = None,
        answer_text: str | None = None,
        category_id: int | None = None,
        tag_ids: list[int] | None = None,
    ) -> QaDetail:
        """
        - 指定されたフィールドのみUPDATEする（Noneは「変更なし」の意味。tag_idsは空リスト[]で「全解除」を表現できるようにし、Noneと[]を区別すること）。
        - question_textが指定された場合、create_qaで生成した1件のquestion_altered行（該当qa_idに紐づく最初の1件、または専用フラグで識別する。5.1節参照）のtextとembeddingを再計算してUPDATEする。
        - tag_idsが指定された場合、qa_tagを「指定された集合に置き換える」（既存分をDELETEしてから指定分をINSERT、またはINSERT/DELETEの差分計算のいずれでもよい）。
        """
        ...

    def list_categories(self) -> list[dict]:
        """[{"id": int, "name": str}, ...] を返す（categoryテーブルの単純SELECT）。"""
        ...
```

**5.1節で触れる「該当qa_idに紐づく最初の1件」の識別方法**: `question_altered` テーブルには現状、自動生成行と既存投入時のLLM生成パラフレーズ行を区別するカラムが存在しない。`update_qa`が誤って既存パラフレーズ行を書き換えないよう、以下のいずれかの対応を実装時に選択すること（詳細設計事項として実装担当者が確定してよいが、選択理由をコードコメントに残すこと）。

- (a) `question_altered` に `is_primary BOOLEAN DEFAULT false` カラムを追加するマイグレーションを追加し、`create_qa`で生成する1件に `is_primary=true` を付与、`update_qa`は `is_primary=true` の行のみを更新対象とする。
- (b) 既存データにはカラム追加を行わず、`create_qa`実行時に生成した`question_altered.id`を`QaDetail`のレスポンスに含めず内部的に記録する方式は状態を持てないため不採用。**(a)を推奨する。**

(a)を採用する場合、マイグレーションSQLは以下の通り。

```sql
ALTER TABLE question_altered
    ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT false;
```

既存データ（LLM生成のパラフレーズ行）の `is_primary` は全件 `false` のままでよい（本フェーズの対象外）。

### 4.2 Knowledge MCP: MCPツール入出力（T2, T3, T4）

**`list_qa` 入力/出力**

```json
// 入力
{ "keyword": "積算", "category": "積算システムの操作方法に関するご質問", "tag_ids": [12], "limit": 20, "offset": 0 }

// 出力
{
  "items": [
    { "id": "1ca063f6-...", "title": "...", "category": "...", "tags": ["積算システムの操作方法"], "question_altered_count": 4 }
  ],
  "total": 1
}
```

**`create_qa` 入力/出力**

```json
// 入力
{ "title": "...", "question_text": "...", "answer_text": "...", "category_id": 3, "tag_ids": [12, 3] }

// 出力（QaDetail）
{ "id": "生成されたuuid", "title": "...", "question_text": "...", "answer_text": "...",
  "category": {"id": 3, "name": "..."}, "tags": [{"id":12,"name":"..."},{"id":3,"name":"..."}],
  "question_altered_count": 1 }
```

**`update_qa` 入力**（指定フィールドのみ更新。`tag_ids`未指定はタグ変更なし、`tag_ids: []`は全解除）

```json
{ "qa_id": "1ca063f6-...", "answer_text": "更新後の回答本文", "tag_ids": [12] }
```

**`list_categories` 出力**

```json
{ "categories": [ {"id": 1, "name": "..."}, {"id": 2, "name": "..."} ] }
```

エラー時は `QaError` を `mcp.server.fastmcp.exceptions.ToolError` へ変換して送出する（既存 `tools.py` の `create_tag` 等と同様のパターン、`knowledge_mcp/src/knowledge_mcp/mcp/tools.py` 参照）。

### 4.3 Knowledge MCP: タグ管理ツール拡張（T6, T7, T8）

`TagRepository` に以下のメソッドを追加する。

```python
class TagRepository:
    # 既存: list_tags / create_tag / rename_tag / move_tag / delete_tag

    def set_tag_description(self, tag_id: int, description: str | None) -> TagNode:
        ...

    def add_tag_alias(self, tag_id: int, alias: str) -> dict:
        """{"id": int, "tag_id": int, "alias": str} を返す。alias重複はTagErrorとする。"""
        ...

    def remove_tag_alias(self, alias_id: int) -> None:
        ...
```

- `create_tag` / `rename_tag` に任意パラメータ `description: str | None = None` を追加する（指定時は作成・変更と同時に`description`も設定する）。
- `delete_tag` は、既存の拒否判定（`qa_tag`参照・子タグ存在）を通過した場合、`DELETE FROM tag_alias WHERE tag_id = %s` を先に実行してから `DELETE FROM tag` を実行するよう変更する（0節の決定に基づくcascade削除）。
- `list_tags` が返す `TagNode.to_dict()` に `description` と `aliases`（`[{"id": int, "alias": str}, ...]`）を追加する（`TagNode` データクラスへのフィールド追加、`models/tag.py` の変更を伴う）。
- `mcp/schemas.py` の `TAG_NODE_SCHEMA` に `description` (`type: ["string", "null"]`) と `aliases` (配列) を追加する。

**既存呼び出し元への影響確認（T8）**: `search_knowledge` の `tags` フィルタは `tag.name` の完全一致のみを使用しており、`description`/`aliases`追加の影響を受けない。Tag Selector MCP は `tag`/`tag_alias` を直接SELECTしており、Knowledge MCPの`list_tags`ツールを呼び出していないため影響を受けない（`docs/requirement/202608051636.md` 5.1節構成図参照）。両者とも後方互換が保たれることをコードレビューで確認すること。

### 4.4 web_backend: MCPクライアントラッパー（T9）

```python
class KnowledgeMcpError(Exception):
    """Knowledge MCP側の業務エラー（QaError/TagError相当）をラップする例外。"""
    def __init__(self, message: str):
        ...


class KnowledgeMcpClient:
    def __init__(self, url: str):
        self.url = url  # 環境変数 KNOWLEDGE_MCP_URL

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """
        MCP Python SDK のStreamable HTTPクライアントを用いて、リクエストごとに
        セッションを新規に張り、ツールを呼び出し、レスポンスを辞書として返す。
        MCPのエラーレスポンス（ToolError相当）を捕捉し、KnowledgeMcpErrorへ変換する。
        呼び出し完了後は必ずセッションをクローズする（0節の決定）。
        """
        ...
```

- FastAPIの非同期エンドポイントから `await client.call_tool("list_qa", {...})` のように呼び出す想定とする。
- 接続先URL（`KNOWLEDGE_MCP_URL`、例: `http://knowledge_mcp:8100/mcp`）は環境変数から読み込む（6章参照）。

### 4.5 web_backend: `/api/qa` エンドポイント（T10, T12, T13）

```python
router = APIRouter(prefix="/api")

@router.get("/qa")
async def list_qa(keyword: str | None = None, category: str | None = None,
                   tag_id: list[int] | None = Query(default=None),
                   limit: int = 20, offset: int = 0) -> QaListResponse:
    ...

@router.get("/qa/{qa_id}")
async def get_qa(qa_id: str) -> QaDetailResponse:
    ...

@router.post("/qa", status_code=201)
async def create_qa(body: QaCreateRequest) -> QaDetailResponse:
    ...

@router.put("/qa/{qa_id}")
async def update_qa(qa_id: str, body: QaUpdateRequest) -> QaDetailResponse:
    ...

@router.get("/categories")
async def list_categories() -> CategoryListResponse:
    ...
```

- Pydanticモデル（`QaListResponse`, `QaDetailResponse`, `QaCreateRequest`, `QaUpdateRequest`, `CategoryListResponse`）は、4.2節のJSON構造にそのまま対応させる。
- `KnowledgeMcpError` を捕捉し、`HTTPException(status_code=409, detail=str(e))` へマッピングする（T13、共通の例外ハンドラとして実装してよい）。

### 4.6 web_backend: `/api/tags` エンドポイント（T11, T13）

```python
router = APIRouter(prefix="/api")

@router.get("/tags")
async def list_tags(parent_tag_id: int | None = None) -> TagListResponse:
    ...

@router.post("/tags", status_code=201)
async def create_tag(body: TagCreateRequest) -> TagResponse:
    ...

@router.put("/tags/{tag_id}")
async def update_tag(tag_id: int, body: TagUpdateRequest) -> TagResponse:
    """
    body に name/description/parent_tag_id のいずれかまたは複数が指定される。
    指定された項目に応じて rename_tag / set_tag_description / move_tag を必要な回数だけ呼び出す
    （Knowledge MCP側は単一項目ごとのツールのため、web_backend側で1回のPUTリクエストから
    複数ツール呼び出しへ変換する）。
    """
    ...

@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: int) -> None:
    ...
```

### 4.7 front_dev: `api.ts` 追加関数（T16）

```typescript
export async function listQa(params: QaListParams): Promise<QaListResponse> { ... }
export async function getQa(id: string): Promise<QaDetail> { ... }
export async function createQa(body: QaCreateRequest): Promise<QaDetail> { ... }
export async function updateQa(id: string, body: QaUpdateRequest): Promise<QaDetail> { ... }

export async function listTags(parentTagId?: number): Promise<TagNode[]> { ... }
export async function createTag(body: TagCreateRequest): Promise<TagNode> { ... }
export async function updateTag(id: number, body: TagUpdateRequest): Promise<TagNode> { ... }
export async function deleteTag(id: number): Promise<void> { ... }

export async function listCategories(): Promise<Category[]> { ... }
```

- いずれも既存 `ask` / `deleteSession` 関数と同様、`fetch` を用いた薄いラッパーとし、`!res.ok` の場合はエラーレスポンス本文（`detail`）を含めた `Error` を送出する（既存パターンを踏襲）。
- エンドポイントは全て `/api/...`（`vite.config.ts` の新規プロキシ設定経由で `web_backend` へ転送される）。

### 4.8 front_dev: `AppAdmin` ルーティング（T15）

```typescript
// main.tsx への追加
if (path.startsWith("/admin")) {
  root = <AppAdmin />;
} else if (path === "/evaluated_messages") {
  ...
} else {
  root = <AppStateless />;
}
```

```typescript
// AppAdmin.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";

export default function AppAdmin() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/admin/qa" element={<QaListPage />} />
        <Route path="/admin/qa/new" element={<QaFormPage mode="create" />} />
        <Route path="/admin/qa/:id" element={<QaFormPage mode="edit" />} />
        <Route path="/admin/tags" element={<TagTreePage />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- `QaFormPage` は `mode` prop と `useParams()`（編集時の `id`）により、新規作成／編集の両方を1コンポーネントで扱う。

## 5. 設定・環境変数一覧（確定表）

| 変数名 | 例 | 用途 |
|---|---|---|
| KNOWLEDGE_MCP_URL | http://knowledge_mcp:8100/mcp | `web_backend` がMCPクライアントとして接続するKnowledge MCPのエンドポイント |

`.env.example` に上記を追記すること（既存の `KNOWLEDGE_MCP_PORT` の下に追記するとよい）。

## 6. `docker-compose.yml` / `vite.config.ts` 変更指示（差分）

### 6.1 `docker-compose.yml`（`web_backend` サービス）

```yaml
  web_backend:
    # ...(既存の記述はそのまま)...
    environment:
      # ...(既存の環境変数はそのまま)...
      - KNOWLEDGE_MCP_URL=${KNOWLEDGE_MCP_URL:-http://knowledge_mcp:8100/mcp}
    depends_on:
      db_hiroba_qa:
        condition: service_healthy
      conversation_db:
        condition: service_healthy
      knowledge_mcp:
        condition: service_healthy
```

- `knowledge_mcp` サービス自体の定義（ポート、ヘルスチェック等）は変更しない。

### 6.2 `vite.config.ts`

```typescript
proxy: {
  // ...(既存のエントリはそのまま)...
  '/api': { target: 'http://app:8000', changeOrigin: true },
},
```

- `/admin` 配下のページパスはVite dev serverのデフォルトのSPAフォールバックにより `index.html` が返るため、既存 `/evaluated_messages` のような `bypass` 分岐は不要（要件定義書9.2節、ADR-0015参照）。ただし、実装時に実際の挙動を確認し、想定通りindex.htmlが返らない場合は`/admin`用の`historyApiFallback`相当の設定を追加すること。

## 7. 実装順序と依存関係（再掲・詳細化）

1. T1〜T5（Knowledge MCP QA管理ツール）とT6〜T8（Knowledge MCP タグ管理ツール拡張）は並行実施可能。いずれも既存 `search_knowledge` / `list_tags` 等の既存ツールの入出力仕様を変更しないこと（後方互換の維持、T8で影響確認）。
2. T9（MCPクライアント）は、T1〜T8で確定したツールの入出力仕様に依存するため、少なくともスキーマが確定した時点で着手する。
3. T10〜T14（web_backend APIエンドポイント）はT9完了後に着手する。
4. T15〜T20（front_dev）は、T10〜T14で確定したAPIレスポンス形式に依存するため、モックレスポンスを用いた並行開発は可能だが、結合確認はT14完了後に行う。
5. T21〜T23（Docker/環境変数）はT9・T14の完了後（接続先・ポート等が確定した時点）に反映する。
6. T24〜T26（検証）は全タスク完了後に実施する。

## 8. テスト・検証指示（Phase 6）

### 8.1 単体テスト観点

- `QaManagementRepository.create_qa` / `update_qa`: 必須項目欠落時のエラー、存在しない`category_id`/`tag_ids`指定時のエラー、`question_text`変更時に`question_altered`（`is_primary=true`の1件）のみが更新されること。
- `QaManagementRepository.list_qa`: keyword/category/tag_idsの組み合わせによる絞り込み結果の正しさ、`limit`/`offset`によるページングの正しさ、`total`が絞り込み後の全件数を返すこと。
- `TagRepository.delete_tag`: 削除時に紐づく`tag_alias`が連動して削除されること。既存の拒否判定（`qa_tag`参照・子タグ存在）は変更後も維持されていること。
- `TagRepository.add_tag_alias`: alias重複時にエラーとなること（`tag_alias.alias`のUNIQUE制約）。
- web_backend: `KnowledgeMcpError`発生時に対応するエンドポイントが409を返すこと（モックしたMCPクライアントを用いる）。

### 8.2 手動疎通確認（T24）

- front_devの `/admin/qa` にアクセスし、QA一覧が表示されること。キーワード・カテゴリ・タグでの絞り込みが機能すること。
- `/admin/qa/new` から新規QAを登録し、一覧・検索結果に反映されること。登録したQAが既存チャット機能（`/ask`）の検索対象に含まれること（`question_altered`が正しく生成されていることの確認を兼ねる）。
- 既存QAを編集（`question_text`を含む）し、保存後の一覧・チャット検索結果に変更が反映されること。
- `/admin/tags` にアクセスし、タグの階層がツリー表示されること。新規タグ作成・名称変更・親タグ変更・削除が行えること。削除不可なタグ（子タグあり、またはQA紐付けあり）は理由が表示され操作が無効化されること。

### 8.3 既存機能への影響確認（T25）

- 既存チャット機能（`/ask`, `/ask-sl`）が本変更の前後で同一の応答をすることを確認する（`data/eval_queries.csv`を用いたMRR比較でも良い）。
- 既存のMCPクライアント（インスペクタ等）から `search_knowledge` / 既存の `list_tags` / `create_tag` 等を呼び出し、入出力仕様が本変更前と後方互換であることを確認する。

## 9. 完了条件（要件定義書11章のDoDに対応する実装レベルの確認項目）

- [ ] `list_qa`/`get_qa`/`create_qa`/`update_qa`/`list_categories` がKnowledge MCPのMCPクライアントから呼び出せる。
- [ ] `create_qa`実行時、`question_altered`が1件自動生成され、embeddingが計算・保存される。
- [ ] `update_qa`で`question_text`を変更した場合、対応する`question_altered`行のみが再計算される（他のパラフレーズ行に影響しない）。
- [ ] `web_backend`の新規APIが、すべてKnowledge MCPのMCPツール経由で処理され、`chatbot_db`への直接書き込みを行っていないことをコードレビューで確認する。
- [ ] front_devのQA一覧・タグ階層ページで、内容・タグ付与状況・階層構造が確認できる。
- [ ] front_devのQA登録編集フォーム・タグ登録編集UIから、それぞれの登録・編集操作が行え、結果が一覧に反映される。
- [ ] タグ削除時、`qa_tag`参照・子タグ存在時は拒否され、削除可能な場合は`tag_alias`も連動して削除される。
- [ ] 既存チャット機能（`/ask`等）、既存Knowledge MCPツール（`search_knowledge`, 既存の`list_tags`等）の動作に影響がない（8.3節）。
- [ ] `docker-compose up` で全サービスが正常起動し、`web_backend`が`knowledge_mcp`のヘルスチェック完了後に起動する。

## 10. 実装時の注意点・落とし穴

- `question_altered`に自動生成行と既存パラフレーズ行が混在する状態になるため、`update_qa`が誤って既存パラフレーズ行を書き換えないよう、4.1節の`is_primary`カラムによる識別を必ず実装すること。これを怠ると、既存データ投入時にLLMで生成された複数パラフレーズの一部が管理UI経由の編集で上書き・消失する事故につながる。
- `TagRepository`・`QaManagementRepository`のいずれも、既存の`TagRepository`と同様に**内部状態としてタグ・QA情報をキャッシュしないこと**（ADR-0006の設計方針を踏襲する。呼び出しの都度DBを参照する）。
- `web_backend`から Knowledge MCP への呼び出しは非同期（`async`）になるため、既存の同期的な`DB`クラス（`src/db.py`）を使った既存エンドポイント（`/ask`等）と混在させる場合、FastAPIのイベントループをブロックしないよう注意する（既存エンドポイントの実装方式は変更しないため、新規追加分のみ非同期呼び出しに統一すればよい）。
- `KNOWLEDGE_MCP_URL`が未設定・接続不可の場合、`/api/qa`等のエンドポイントは全て失敗する。起動時のヘルスチェック依存関係（6.1節）に加えて、接続失敗時にfront_dev側で分かりやすいエラーメッセージが表示されることを確認する。
- タグの`description`/`aliases`拡張（T6〜T8）は、既存Tag Selector MCPが参照する`tag`/`tag_alias`テーブルへの書き込みでもある。Tag Selector MCP側の`reload_taxonomy`実行後に新しい内容が反映されることを、本フェーズの受け入れ確認（9章）に含めること。
- `front_dev`の`/admin`配下ルーティング追加により、Vite dev serverのSPAフォールバック挙動が既存3画面のpathname分岐と干渉しないことを実機で確認すること（6.2節の注記）。
- `list_qa`の絞り込み条件（keyword/category/tag_ids）の組み合わせクエリは、既存`QARepository.search`のtags/category条件のSQL（`knowledge_mcp/src/knowledge_mcp/repository/qa_repository.py`）を参考にできるが、`QaManagementRepository`はembedding類似検索を行わない単純な条件検索であるため、同じSQLパターンを流用しつつベクトル距離処理は除外すること。

## 11. 実装着手前に確認をお願いしたい事項（再掲）

本書 0節の内容（QA・タグ削除の扱い、認証方式、MCPクライアント実装方式、`tag_alias`のcascade削除方針を含む）は、いずれも発注者により承認済みであり、実装着手可能な状態にある。

残る主な検討事項:

- **書き込み系API（QA・タグの登録編集削除）のアクセス制御**（要件定義書Open Issue #2）。
- **QA・タグの削除機能の要否とcascade方針**（要件定義書Open Issue #1）。
- **`front_dev`の位置付けの見直し**（要件定義書Open Issue #7、デバッグUIから管理ツールへの性格変化）。
