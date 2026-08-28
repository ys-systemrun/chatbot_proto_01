# 言い換え質問文（question_altered）管理機能 要件定義書

- 文書番号: REQ-202608271750
- 対象プロジェクト: chatbot_invitro
- 対象コンポーネント: `knowledge_mcp`（新規MCPツール）, `web_backend`（新規API）, `front_dev`（新規管理画面）
- 変更なしのコンポーネント: `qa_original`/`question_altered`/`tag`/`qa_tag`テーブルのスキーマ、既存の`create_qa`/`update_qa`/`import_qa_batch`、既存の全データエクスポート機能（`/api/export`）、`tag_selector_mcp`、`agent_invitro`
- 参照資料: `docs/requirement/202608060826_QAタグ管理UI要件定義書.md`、`docs/requirement/202608241530_全データエクスポート機能要件定義書.md`、`docs/requirement/202608261002_DBマイグレーション・データインポート機能要件定義書.md`、`docs/requirement/202608261600_タグデータ一括インポート機能要件定義書.md`
- 前提の決定事項: 本書末尾「13. 関連ADR一覧」参照

## 1. 目的

`question_altered`テーブル（QAの言い換え質問文・embeddingを保持するテーブル）を対象に、一覧確認・CSV一括インポート・新規作成・編集・削除ができる管理画面と、対応するCSVエクスポート機能を追加する。

現状、`question_altered`行は、QA登録・編集フォーム（`front_dev`の`QaFormPage`）経由の`create_qa`/`update_qa`が、`qa_original.question_text`に対応する主質問文行（`is_primary=true`）を自動生成・自動更新するのみであり、初期データ投入時にLLMで生成された言い換え行（`is_primary=false`、パラフレーズ）を、一覧・検索・追加・編集する手段がない（ADR-0014 Open Issue、要件定義書202608060826 Open Issue #3）。本書はこのOpen Issueに対応し、言い換え行を対象とした管理機能を新設する。

## 2. 背景・参照資料

- `question_altered`テーブルは `id`（`SERIAL PK`）, `qa_id`（`qa_original.uuid`を指すが外部キー制約なし）, `text`, `embedding`（`VECTOR(N)`、次元は環境変数`EMBEDDING_VECTOR_DIM`依存）, `is_primary`（`BOOLEAN NOT NULL DEFAULT false`）から構成される（`db_hiroba_qa_init/migrations/0002_question_altered_table.py`, `0004_add_question_altered_is_primary.sql`）。
- `create_qa`/`update_qa`（ADR-0014）は、`question_text`の登録・変更のたびに、`is_primary=true`の行を常に1件だけ生成・再計算する。既存の複数言い換え行（`is_primary=false`）には触れない。
- QA・タグの一括インポート（`import_qa_batch`, ADR-0053）、タグ単体の一括インポート（`import_tag_batch`, ADR-0061）は、いずれも「Knowledge MCPに薄いバッチツールを追加し、既存の単発処理のバリデーション・業務ロジックをループ適用する」という同一の設計方針を採っている。本書もこの方針を踏襲する。
- 全データエクスポート機能（ADR-0046/0047）は、`chatbot`データベース読み取り専用ロールを介して8テーブル分のCSV/SQLをZIPで一括ダウンロードする機能を既に提供しており、`question_altered.csv`は`id`/`qa_id`/`text`/`is_primary`の4列（`embedding`を除く）で出力される。本書が新設するCSVエクスポートは、この既存機能とは別に、`question_altered`単体を「そのまま再インポートできる形式」で出力する機能として独立に追加する（両機能の関係整理は5章・10章を参照）。
- 本書は、発注者との確認を経て、次の方針を確認済みである。
  1. 対象範囲: `is_primary=false`の言い換え行のみを新機能の対象とする。`is_primary=true`の主質問文行は、引き続き既存のQA登録編集フォーム（`create_qa`/`update_qa`）のみが生成・更新する。
  2. `is_primary`の一意性: 新機能は`is_primary=true`行を一切生成・変更しない（常に`false`固定で作成し、`is_primary=true`行の更新は拒否する）ことで、「`qa_id`ごとに`is_primary=true`行は常に1件」という既存の前提を維持する。
  3. CSV一括インポートの重複判定: `id`列によるupsert方式（`id`空欄=新規作成、既存`id`一致=更新）とする。
  4. 新規作成・編集ページでの対象QA指定方法: タイトル・質問文の部分一致検索によるQA検索ピッカーを新設し、`qa_id`を選択する。
  5. CSVエクスポートの対象範囲: `is_primary=false`の言い換え行のみとし、列構成をCSVインポートと一致させることで、そのまま再インポートできる形式にする。
  6. 削除機能: 一覧・編集ページから、言い換え行（`is_primary=false`）を1件単位で削除できるようにする。CSV経由の一括削除は対象外とする（4.2節）。

## 3. 用語定義

| 用語 | 説明 |
|---|---|
| 言い換え質問文（question_altered） | `question_altered`テーブルの1行。QAに対する言い換え表現（パラフレーズ）とそのembeddingを保持する |
| 主質問文行 | `question_altered.is_primary = true`の行。`qa_original.question_text`と対応し、`create_qa`/`update_qa`のみが生成・更新する。1つの`qa_id`につき常に1件である前提を維持する |
| 言い換え行 | `question_altered.is_primary = false`の行。本書が新設する管理機能（一覧・新規作成・編集・削除・CSVインポート/エクスポート）の対象 |
| upsert（アップサート） | `id`の一致を基準に、既存行があれば更新、なければ新規作成する処理方式（本書ではCSVインポートに適用） |
| QA検索ピッカー | 新規作成・編集ページで、対象`qa_id`をタイトル・質問文の部分一致検索から選択するための新規UIコンポーネント |

## 4. スコープ

### 4.1 対象範囲（MVP）

- `front_dev`に、言い換え行の一覧ページ・新規作成ページ・編集ページを新設する（`/admin`サブツリー、ADR-0015の方針を踏襲）。
- 一覧ページは、`qa_id`（QA検索ピッカーによる絞り込み）・`text`のキーワード部分一致で絞り込み、ページングして表示する。各行から編集ページへ遷移できる。
- 新規作成ページは、QA検索ピッカーで対象`qa_id`を選択し、`text`を入力して言い換え行を1件追加する（`is_primary`は常に`false`固定、UI上で選択させない）。
- 編集ページは、既存の言い換え行の`text`を変更する（`qa_id`は変更不可）。編集ページには「削除」ボタンを設け、確認ダイアログのうえ対象の言い換え行を削除できる。
- 一覧ページの各行にも削除操作（確認ダイアログを伴う）を設ける。削除対象は`is_primary=false`行に限り、`is_primary=true`行（主質問文行）は削除できない。
- 一覧ページに、CSVアップロードによる一括インポート機能（QA一括インポート`QaListPage`と同様のUIパターン: アップロードボタン＋行ごとの結果一覧表示）を追加する。
- 一覧ページに、現在の絞り込み条件に関わらず言い換え行全件をCSVとしてダウンロードするエクスポート機能を追加する。エクスポートしたCSVは、列構成をインポートと一致させることで、そのまま再インポートできる。
- `knowledge_mcp`に、言い換え行を対象とした新規MCPツール（`list_question_altered`/`get_question_altered`/`create_question_altered`/`update_question_altered`/`delete_question_altered`/`import_question_altered_batch`/`export_question_altered`）を追加する。
- `web_backend`に、これらのツールをREST API化する新規エンドポイント（`/api/question_altered/*`）を追加する。CSVの構文解析（列の存在チェック等の機械的なバリデーション）のみを`web_backend`が担い、業務バリデーション（`qa_id`の存在確認、`is_primary=true`行への操作拒否等）はKnowledge MCP側に委ねる（ADR-0013の既存方針を維持）。

### 4.2 対象外（将来検討・別スコープ）

- **主質問文行（`is_primary=true`）の新規作成・編集・削除**: 引き続き既存のQA登録編集フォーム（`create_qa`/`update_qa`）のみが行う。本機能では一覧上での参考表示も含め対象としない（一覧は`is_primary=false`行のみを表示する）。
- **CSV経由の一括削除**: 削除機能は一覧・編集ページからの個別操作（確認ダイアログを伴う）のみを対象とし、CSVインポートに削除指定列（例: `delete`フラグ）を設けた一括削除は本書のMVPには含めない。誤操作時に大量の行が一括で消えるリスクを避けるための判断であり、必要になった場合は別途要件化する（12章 Open Issue参照）。
- **言い換え行から主質問文行への昇格（`is_primary`の切り替え）**: `is_primary=true`行は`qa_original.question_text`との同期が前提となっており、この同期処理を新機能に持ち込むと`update_qa`との二重実装になるため対象外とする（ADR-0064）。
- **`qa_id`の付け替え（既存の言い換え行を別のQAへ移動する編集）**: 本書の編集機能は`text`の変更のみを対象とし、`qa_id`は作成後固定とする。
- **CSVインポートにおける新規タグ自動作成等、タグ・カテゴリに関する処理**: `question_altered`はタグ・カテゴリを持たないため対象外。
- **アクセス制御の強化**: 既存の管理画面群と同様、ネットワークレベルの制限（社内IPアドレス限定, ADR-0041）のみとし、追加のログイン認証は設けない。
- **既存の全データエクスポート機能（ADR-0047）の変更**: `is_primary=true`行を含む全件を8テーブルのZIPとして出力する既存機能は変更しない。本書のCSVエクスポートとは対象範囲・目的・実装経路が異なる独立した機能として併存させる。

## 5. 全体アーキテクチャ

### 5.1 システム構成（本フェーズ）

```
front_dev（新規: QuestionAlteredListPage / QuestionAlteredFormPage / QaPicker）
        │  GET/POST/PUT /api/question_altered/*
        ▼
web_backend（新規: question_altered_controller.py、CSVパース・API変換のみ）
        │  MCPツール呼び出し（既存の書き込み・読み取り経路、ADR-0013を維持）
        ▼
knowledge_mcp（新規ツール: list/get/create/update/delete/import_batch/export）
        │  既存 QaManagementRepository の embed_fn・qa_id存在検証ロジックを再利用
        ▼
chatbot データベース（question_altered テーブル、is_primary=false 行のみ書き込み対象）
```

- `tag_selector_mcp`・`agent_invitro`・既存の全データエクスポート（`web_backend/src/export/`、ADR-0046/0047の読み取り専用ロール経路）には変更を加えない。
- 言い換え行の一覧・作成・編集・CSVインポート・CSVエクスポートのすべてを、`web_backend → knowledge_mcp`経由の同一経路で実装する（読み取り・書き込みいずれもKnowledge MCP経由とするADR-0013の原則を、エクスポートにも適用する）。

### 5.2 コンポーネント一覧と責務（追加・変更分）

| コンポーネント | 変更内容 |
|---|---|
| `knowledge_mcp`（新規ツール） | 言い換え行の一覧・詳細・新規作成・編集・削除・CSV一括インポート・CSVエクスポートを行う新規MCPツール7件の追加 |
| `web_backend`（新規API） | `/api/question_altered/*`（一覧・詳細・作成・編集・削除・CSVインポート・CSVエクスポート）の追加。既存`qa_controller.py`と同様、MCPツール呼び出しのみを行うBFF |
| `front_dev`（新規画面） | 一覧ページ・新規作成ページ・編集ページ（削除操作を含む）、QA検索ピッカーコンポーネント、管理画面ナビへのメニュー項目追加 |

## 6. 機能要件

### 6.1 front_dev: 言い換え行一覧ページ（`QuestionAlteredListPage`、仮称）

- ルート: `/admin/question_altered`。
- QA検索ピッカーによる`qa_id`絞り込み、`text`のキーワード部分一致絞り込み、ページング（既存`QaListPage`と同様のUIパターン）。
- 一覧の各行に、対象QAのタイトル（`qa_original.title`）・`text`・編集リンクを表示する。
- 「新規作成」ボタン（`/admin/question_altered/new`へ遷移）、「CSVインポート」ボタン、「CSVエクスポート」ボタンを配置する。

### 6.2 front_dev: 新規作成・編集フォーム（`QuestionAlteredFormPage`、仮称）

- ルート: `/admin/question_altered/new`（新規作成）、`/admin/question_altered/:id`（編集）。既存`QaFormPage`の`mode`プロパティによる単一コンポーネント構成を踏襲する。
- 新規作成モード: QA検索ピッカー（新設コンポーネント。既存`GET /api/qa?keyword=...`をタイトル・質問文の部分一致検索として再利用し、候補を絞り込んで`qa_id`を選択する）と`text`入力欄を表示する。
- 編集モード: 対象`qa_id`・対象QAのタイトルを読み取り専用で表示し、`text`のみ編集可能とする。
- 保存時、新規作成は`POST /api/question_altered`、編集は`PUT /api/question_altered/{id}`を呼び出す。
- 編集モードには「削除」ボタンを配置し、確認ダイアログのうえ`DELETE /api/question_altered/{id}`を呼び出す。削除成功後は一覧ページへ遷移する。

### 6.3 front_dev: QA検索ピッカー（`QaPicker`、仮称）

- タグ選択に使われている既存`TagPicker.tsx`と同様の位置付けで、QA一覧ページ・言い換え行新規作成ページの両方から利用できる共通コンポーネントとして新設する。
- 入力したキーワードで`GET /api/qa?keyword=...&limit=10`（既存エンドポイント）を呼び出し、候補（タイトル・カテゴリ）を表示して選択させる。新規エンドポイントの追加は不要。

### 6.4 front_dev: CSVインポートUI

- 一覧ページに、既存QA一括インポート（`QaListPage`）と同様のパターン（ファイル選択＋アップロードボタン＋結果一覧表示）でCSVアップロードUIを追加する。
- インポート結果（成功件数、行ごとのエラー内容）を画面に一覧表示する。一部の行がエラーになっても他の行の処理は継続する（行単位の部分成功を許容、ADR-0053と同様の方針）。

### 6.5 front_dev: CSVエクスポートUI

- 一覧ページに「CSVエクスポート」ボタンを追加し、クリックで`GET /api/question_altered/export`を呼び出し、レスポンスのBlobをブラウザのファイル保存ダイアログにつなげる（既存`ExportPage`のダウンロード処理と同様のパターン）。
- 一覧ページの絞り込み条件（`qa_id`・キーワード）には依存せず、言い換え行全件を対象とする（MVPでは絞り込み結果のみのエクスポートは対象外とし、12章のOpen Issueとする）。

### 6.6 web_backend: 新規APIエンドポイント（BFF）

| メソッド・パス | 説明 |
|---|---|
| `GET /api/question_altered` | 言い換え行一覧。クエリパラメータ: `qa_id`, `keyword`, `limit`, `offset` |
| `GET /api/question_altered/{id}` | 言い換え行詳細 |
| `POST /api/question_altered` | 新規作成。リクエストボディ: `{qa_id, text}` |
| `PUT /api/question_altered/{id}` | 編集。リクエストボディ: `{text}` |
| `DELETE /api/question_altered/{id}` | 削除。対象が`is_primary=true`の場合はエラー |
| `POST /api/question_altered/import` | CSV一括インポート（`multipart/form-data`でCSVファイルを受け取る） |
| `GET /api/question_altered/export` | CSVエクスポート（`is_primary=false`行全件、`Content-Disposition: attachment`でダウンロード） |

いずれのエンドポイントも、既存`qa_controller.py`と同様、対応するKnowledge MCPツールを呼び出すのみとし、`chatbot`データベースへの直接アクセスは行わない。

### 6.7 Knowledge MCP: 新規ツール（ADR-0064）

| ツール名 | 説明 |
|---|---|
| `list_question_altered` | `qa_id`（任意）・`keyword`（任意、`text`部分一致）・`limit`/`offset`で言い換え行（`is_primary=false`のみ）を一覧する。表示用に`qa_original.title`を結合して返す |
| `get_question_altered` | 言い換え行の詳細を`id`指定で取得する |
| `create_question_altered` | `qa_id`（必須、存在検証）・`text`（必須）を受け取り、`embed_fn`でembeddingを計算し、`is_primary=false`固定で1件追加する |
| `update_question_altered` | `id`（必須）・`text`（必須）を受け取り、対象行の存在と`is_primary=false`であることを検証したうえで`text`とembeddingを再計算する。対象が`is_primary=true`の場合はエラーを返す |
| `delete_question_altered` | `id`（必須）を受け取り、対象行の存在と`is_primary=false`であることを検証したうえで削除する。対象が`is_primary=true`の場合はエラーを返す |
| `import_question_altered_batch` | CSV由来の複数行をまとめて登録・更新する。`id`空欄は新規作成（`is_primary`列の値は無視し常に`false`固定）、`id`一致は更新（対象が`is_primary=true`の場合はエラー行として報告）とする。行単位でエラーを許容する（ADR-0053/0061と同様の方針） |
| `export_question_altered` | 言い換え行（`is_primary=false`）全件を、ページングせず`id`/`qa_id`/`text`/`is_primary`の4列で返す（CSV組み立ては`web_backend`側で行う） |

### 6.8 主質問文行（`is_primary=true`）との関係整理

- 本機能は`is_primary=true`行を新規作成・編集・削除しない。既存の`create_qa`/`update_qa`の挙動・シグネチャは変更しない。
- CSVエクスポートは`is_primary=false`行のみを対象とするため、既存の全データエクスポート（ADR-0047、`is_primary`を問わず全件）の`question_altered.csv`とは出力内容が異なる。両者を混同しないよう、エクスポートファイル名・画面上の説明文で区別を明示する（例: 本機能は`question_altered_paraphrases_<timestamp>.csv`のようなファイル名とする、詳細設計フェーズで確定）。
- 全データエクスポートのZIP内`question_altered.csv`（`is_primary=true`行を含む）を誤って本機能のCSVインポートへアップロードした場合、`is_primary=true`行に対応する行はエラーとして拒否され、`is_primary=false`行のみが処理される（想定内の挙動とする）。

## 7. データ要件

### 7.1 対象テーブル（再掲、変更なし）

| テーブル | 列 | 本機能での扱い |
|---|---|---|
| `question_altered` | `id`, `qa_id`, `text`, `embedding`, `is_primary` | `is_primary=false`行のみ読み書き対象。スキーマ変更なし |
| `qa_original` | `uuid`, `title`, `question_text` 等 | `qa_id`の存在検証、一覧・ピッカー表示用のタイトル参照のみ（読み取りのみ、変更なし） |

### 7.2 CSVフォーマット（案、インポート・エクスポート共通）

| 列名 | 必須 | 説明 |
|---|---|---|
| `id` | 任意 | 空欄は新規作成、既存`question_altered.id`と一致する場合は更新対象として扱う |
| `qa_id` | 新規作成時必須 | 対象QAの`qa_original.uuid`。既存`qa_original`に存在することを検証する。更新時、既存行の`qa_id`と異なる値が指定された場合はエラーとする（付け替え非対応、4.2節） |
| `text` | 必須 | 言い換え質問文の本文 |
| `is_primary` | 出力のみ（入力は無視） | エクスポート時は常に`false`。インポート時、この列に`true`が指定されていても無視する（`id`が既存の`is_primary=true`行を指す場合は別途エラーとする） |

`embedding`列は含めない（既存の全データエクスポートCSVと同様、`text`変更時にサーバー側で再計算するため）。文字コード（UTF-8 BOM付き可）等の詳細は、既存のQA一括インポート（ADR-0053）のCSV仕様に合わせることを基本方針とし、詳細設計フェーズで確定する（12章 Open Issue #1）。

### 7.3 API入出力例（`GET /api/question_altered`）

```json
{
  "items": [
    {
      "id": 123,
      "qa_id": "1b2c3d4e-...",
      "qa_title": "パスワードを忘れた場合の対処方法",
      "text": "パスワードを忘れてログインできません",
      "is_primary": false
    }
  ],
  "total": 42
}
```

## 8. 非機能要件

| 分類 | 要件 |
|---|---|
| 部分失敗時の扱い | CSVインポートは行単位でエラーを許容し、成功した行は反映され、失敗した行のみエラーとして報告する（既存QA一括インポートと同一方針） |
| ファイルサイズ・件数 | CSV一括インポート・エクスポートの上限件数・ファイルサイズは、既存のQA一括インポートの想定規模を目安とし、詳細は実装フェーズで確定する（12章 Open Issue #2） |
| embedding計算の所要時間 | `create_question_altered`/`update_question_altered`/`import_question_altered_batch`は、既存の`create_qa`/`update_qa`と同様、embedding計算（LM Studio/Bedrock APIへのHTTP呼び出し）を含むため、一覧・検索系ツールより応答時間が長くなる。タイムアウト・エラーハンドリング方針は詳細設計フェーズで確定する |
| アクセス制御 | 既存の管理画面群と同様、ネットワークレベルの制限（社内IPアドレス限定, ADR-0041）のみとし、追加のログイン認証は設けない |
| ログ | 既存の管理系操作ログ（`log_admin_operation`）と同様の方式で、新規作成・編集・CSVインポートの実行を記録する |
| データ整合性 | `is_primary=true`行への操作拒否、`qa_id`存在検証は、Knowledge MCP側のバリデーションとして必ず行い、`web_backend`側での緩和は行わない |

## 9. インフラ・実行環境要件

- 追加のインフラ変更は想定しない。既存の`knowledge_mcp`・`web_backend`・`front_dev`のコンテナ構成（ローカルdocker-compose・AWS ECS Fargate）をそのまま利用する。
- 新規の環境変数追加は想定しない（既存の`KNOWLEDGE_MCP_URL`、embedding接続設定をそのまま利用する）。

## 10. 既存システムとの関係・影響範囲

- `question_altered`/`qa_original`のスキーマは変更しない。
- 既存の`create_qa`/`update_qa`/`import_qa_batch`（ADR-0014/0053）の実装・シグネチャには変更を加えない。`is_primary=true`行の生成・更新は引き続きこれらのツールのみが行う。
- 既存の全データエクスポート機能（`/api/export`、ADR-0046/0047）には変更を加えず、独立した別機能として併存させる。
- `search_knowledge`（ベクトル類似検索）は、言い換え行（`is_primary=false`を含む全`question_altered`行）を検索対象とする既存の挙動のまま変更しない。本機能で追加・編集された言い換え行も、既存の検索ロジックにそのまま反映される（新たな連携実装は不要）。
- `tag_selector_mcp`・`agent_invitro`には影響しない。

## 11. 受け入れ基準（Definition of Done, MVP）

- [ ] 言い換え行一覧ページで、QA検索ピッカーによる`qa_id`絞り込み・キーワード絞り込み・ページングができる。
- [ ] 新規作成ページで、QA検索ピッカーから対象QAを選び、言い換え行を1件追加できる（追加後、`search_knowledge`の検索対象に反映される）。
- [ ] 編集ページで、既存の言い換え行の`text`を変更でき、embeddingが再計算される。
- [ ] `is_primary=true`行（主質問文行）は、一覧・新規作成・編集・削除のいずれからも作成・変更・削除できない。
- [ ] 一覧・編集ページから言い換え行を削除でき（確認ダイアログを伴う）、削除後は一覧・検索結果に表示されなくなる。
- [ ] CSVをアップロードし、複数件の言い換え行が`id`によるupsertで一括登録・更新できる。CSV内の`id`が既存の`is_primary=true`行を指す場合、その行のみエラーとして報告され、他の行の処理は継続する。
- [ ] 一覧ページからCSVエクスポートを行い、ダウンロードしたCSVをそのまま再度インポートしても、内容が変化しない（往復の整合性）。
- [ ] 既存のQA登録編集フォーム、QA一括インポート、既存の全データエクスポート、`search_knowledge`の動作に影響がないことを確認する。

## 12. Open Issues（要追加確認事項）

1. **CSVフォーマットの最終確定**: 7.2節に示した列構成（`id`/`qa_id`/`text`/`is_primary`）は現時点では案であり、区切り文字・文字コードを含め詳細設計フェーズで最終確定する。
2. **ファイルサイズ・件数上限**: 8章に記載の通り、具体的な上限値（CSV行数、ファイルサイズ）は実装フェーズで確定する。
3. **絞り込み結果のみのCSVエクスポート**: MVPでは言い換え行全件を対象とするが、一覧の絞り込み条件（`qa_id`等）に応じた部分エクスポートが必要かどうかは、運用開始後の要望を踏まえて別途要件化する。
4. **CSV経由の一括削除**: 4.2節の通り本書のMVPでは一覧・編集ページからの個別削除のみを対象とし、CSVインポートによる一括削除は対象外とするが、運用開始後に大量の行をまとめて削除したいという要望が出た場合、別途要件定義・ADRが必要になる。
5. **言い換え行から主質問文行への昇格**: 4.2節・ADR-0064の通り対象外とするが、将来的に`is_primary`の切り替えを可能にしたいという要望が出た場合、`qa_original.question_text`との同期方法を含めて別途設計が必要になる。
6. **エクスポートファイル名・画面上の説明文の確定**: 6.8節に記載の、既存の全データエクスポートとの混同防止のための表示・命名の詳細は、実装フェーズで確定する。
7. **主質問文行（is_primary=true）の削除手段**: `delete_question_altered`は主質問文行を削除できない仕様とするため、既存システム全体で主質問文行の削除手段がない状態が続く。QA自体の削除機能（`delete_qa`）が別途必要かどうかも含め、要望が出た場合に別途要件化する。

## 13. 関連ADR一覧

| ADR | タイトル | 決定内容 |
|---|---|---|
| ADR-0064 | 言い換え質問文（question_altered）管理機能の実装方式 | Knowledge MCPに新規ツール群（一覧・詳細・新規作成・編集・削除・CSV一括インポート・CSVエクスポート）を追加し、`is_primary=false`行のみを対象とする。CSVインポート/エクスポートは`id`によるupsertとし、既存の全データエクスポート（読み取り専用ロール経路）とは独立した経路（Knowledge MCP経由）で実装する。削除はCSV経由ではなく一覧・編集ページからの個別操作に限定する |

以下は既存の関連ADR（前提として踏襲する）:

| ADR | タイトル | 決定内容 |
|---|---|---|
| ADR-0013 | 管理UIからのQA・タグ書き込み経路をKnowledge MCP経由に統一する | 本書の新規エンドポイントもこの原則を維持し、読み取り・書き込みいずれもKnowledge MCP経由とする |
| ADR-0014 | QAデータの登録・編集機能をKnowledge MCPのツールとして追加する | `create_qa`/`update_qa`による主質問文行（`is_primary=true`）の自動生成・更新、embedding計算（`embed_fn`）の既存実装。本書の言い換え行管理はこの前提を壊さない設計とする |
| ADR-0015 | front_dev管理画面のルーティング方式 | 本書の新規ページも`/admin`サブツリー限定で`react-router-dom`のルーティングに従う |
| ADR-0046 | chatbotデータベースのエクスポート専用読み取り経路の新設 | 既存の全データエクスポートが用いる読み取り専用ロール。本書のCSVエクスポートはこの経路を使わず、Knowledge MCP経由の別経路とする |
| ADR-0047 | 全データエクスポート機能のダンプ生成方式・配信方式 | 既存の`question_altered.csv`列構成（`id`/`qa_id`/`text`/`is_primary`、`embedding`除外）。本書のCSVエクスポートはこの列構成を踏襲しつつ、対象行（`is_primary=false`のみ）と実装経路が異なる独立機能とする |
| ADR-0053 | QA・タグデータの一括インポート機能の実装方式 | 本書のCSVインポートが踏襲する行単位エラー許容・既存ロジックのループ適用というバッチツール設計パターン |
| ADR-0061 | タグ単体の一括インポート機能の実装方式 | 同上。独立ドメイン（タグ）に対する専用バッチツール新設の先例 |

各ADRの詳細は`docs/adr/`配下を参照。
