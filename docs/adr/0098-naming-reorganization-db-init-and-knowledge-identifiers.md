# ADR-0098: 環境 destroy を機にした命名の全面整理 — `db_hiroba_qa_init`→`db_init`、ナレッジDB系識別子の `chatbot`→`knowledge` 統一、データ・ローカルボリュームの再配置

- ステータス: Accepted
- 日付: 2026-10-05
- 関連: ADR-0016〜0018（yoyo マイグレーション・シード）、ADR-0030（db_hiroba_qa_init の AWS 展開）、ADR-0034（シード元データのイメージ同梱）、ADR-0037 / ADR-0039（Terraform state 分割・2層構成）、ADR-0040（デプロイオーケストレーター）、ADR-0046 / ADR-0047（エクスポート）、ADR-0051 / ADR-0052（conversation DB の yoyo 化・DBロール分離）、ADR-0055 / ADR-0066（全データインポート）、**ADR-0069 / ADR-0077（本ADRが命名方針の一部を上書き）**、ADR-0076（トラブルシューティング情報源）、ADR-0097（DVC によるデータバージョン管理。管理単位を本ADRのディレクトリ構成に合わせる）

## コンテキスト

ナレッジ DB は、ADR-0069・ADR-0076・ADR-0077 を経て、維津美の広場 QA 専用の DB からトラブルシューティング記事などの複数の情報源を載せる基盤（実DB名 `db_chatbot_knowledge_base`）に変わった。ところが、周辺の識別子は経緯をそのまま引きずっており、**同じものに4つの呼び名が混在している**。

| 呼び名 | 由来 | 主な使用箇所 |
|---|---|---|
| `db_hiroba_qa_init` / `db-hiroba-qa-init` | 広場 QA 専用だった頃のサービス名 | ディレクトリ、`pyproject.toml`、docker-compose のサービス名、ECR リポジトリ、CloudWatch ロググループ（`/ecs/db-hiroba-qa-init`）、deploy の Python コードとテスト。docs 以外で約30ファイル |
| `chatbot` | 最初の実DB名 | DB ロール（`chatbot_app` / `chatbot_migrator` / `chatbot_export_reader`）、環境変数（`CHATBOT_DB_NAME` / `CHATBOT_APP_*` / `CHATBOT_EXPORT_DB_URL` など）、Secrets Manager の名前、ダンプファイル名（`chatbot.sql`）、`import-data --target chatbot`、定数（`CHATBOT_TABLES`）、エクスポート画面の説明文 |
| `db_support_knowledge` | ADR-0069 で付けたサーバ名 | docker-compose のサービス名と接続ホスト名 |
| `db_chatbot_knowledge_base` | ADR-0077 で付けた実DB名 | 実DB名 |

さらに、次の問題もある。

- `db_hiroba_qa_init` は、ナレッジ DB と conversation DB の**両方の**マイグレーション・シード・全データインポート・アドホック SQL（ADR-0083）を担っている。名前（広場 QA の初期化）と責務が合っていない。
- `db_hiroba_qa_init/data/` の中に、広場 QA とトラブルシューティング記事の HTML、フル版と縮小版（`*_small`）が同じ階層に並んでいる。ADR-0097 の DVC 管理単位を決めにくい。
- ローカルの DB ボリュームは `db_nomic/data`（ナレッジ）と `db_conversation/data`（会話）に置かれている。同じディレクトリにある `init.sql` は docker-compose からのマウントが廃止されており、使われていない。`db_multilingual/` も使われていない。

ADR-0069 と ADR-0077 では、`chatbot` を冠する識別子やサーバ名 `db_support_knowledge` を**変更しない**と決めていた。AWS の RDS・Secrets・ECR を作り直すコストを避けるためである。しかし今回、**AWS 検証環境の database 層と app 層をいずれも destroy した**。名前を変えても AWS 側で移行や置換をする必要がなく、作り直しのコストが最も小さい時期である。

## 決定

**AWS 環境が destroy された今を利用して、命名を次の語彙に統一する。移行は ADR-0069 と同じ「再構築＋再インポート」方式で、1回のリリースでまとめて行う。**

### 1. 命名の原則

| 語 | 意味 | 使ってよい範囲 |
|---|---|---|
| `chatbot` / `chatbot_invitro` / `chatbot-invitro` | プロダクト・プロジェクト名 | コンテナ名の接頭辞、`name_prefix`、state バケット、bat の内部変数など、プロジェクトを指すものだけ |
| `knowledge` | ナレッジ DB（`db_chatbot_knowledge_base`） | ナレッジ DB のロール・環境変数・シークレット・ダンプ・定数 |
| `conversation` | 会話 DB（`conversation`） | 現行のまま |
| `hiroba` | 維津美の広場が由来のデータ | 広場由来のテーブル（`hiroba_qa_original` / `hiroba_category` / `hiroba_question_altered` / `hiroba_qa_tag`）、それに対応する API パス・画面・データディレクトリだけ |

### 2. 名前の対応表

| 区分 | 現在 | 変更後 |
|---|---|---|
| DB 初期化・運用サービス | ディレクトリ `db_hiroba_qa_init/`、`pyproject` の name、docker-compose のサービス名 | `db_init/`、`db_init`、`db_init`（コンテナ名 `chatbot_db_init` はそのまま） |
| 同上（AWS） | ECR `db-hiroba-qa-init`、ロググループ `/ecs/db-hiroba-qa-init`、タスク family | `db-init`、`/ecs/db-init`、`db-init`。terraform モジュール名 `db-init-task` と揃う |
| ナレッジ DB のホスト（ローカル） | サービス名 `db_support_knowledge`、コンテナ名 `chatbot_db` | `knowledge_db`、`chatbot_knowledge_db`。`conversation_db` と対になる |
| DB ロール | `chatbot_app` / `chatbot_migrator` / `chatbot_export_reader` | `knowledge_app` / `knowledge_migrator` / `knowledge_export_reader` |
| 環境変数 | `CHATBOT_DB_NAME`、`CHATBOT_APP_ROLE_NAME`、`CHATBOT_APP_PASSWORD`、`CHATBOT_MIGRATOR_*`、`CHATBOT_EXPORT_DB_URL` など `CHATBOT_*` のうちナレッジ DB を指すもの | `KNOWLEDGE_DB_NAME`、`KNOWLEDGE_APP_ROLE_NAME`、… 一律 `KNOWLEDGE_*` |
| Terraform | `var.db_name`、Secrets の `name_prefix` に含まれる `-chatbot-*`、出力 `chatbot_*_secret_arn` | `var.knowledge_db_name`（`conversation_db_name` と対）、`-knowledge-*`、`knowledge_*_secret_arn` |
| 全データエクスポート・インポート | `chatbot.sql`、`--target chatbot`、`--chatbot-sql`、`CHATBOT_TABLES` | `knowledge.sql`、`--target knowledge`、`--knowledge-sql`、`KNOWLEDGE_TABLES` |
| 画面の文言 | エクスポート画面の「chatbot データベース」 | 「ナレッジ データベース」 |

**変更しないもの**

- 実DB名 `db_chatbot_knowledge_base` と `conversation`。直近の ADR-0077 で、複数の情報源を載せる実態に合わせて付けたばかりで、意味もずれていない。
- 広場由来のテーブル名 `hiroba_*` と、API パス `/api/hiroba_question_altered`。名前どおり広場由来のデータであり、ADR-0069 の接頭辞方針を引き継ぐ。
- Terraform state の key、`name_prefix` の値、state バケット。

### 3. シード元データのディレクトリ構成（ADR-0097 の DVC 管理単位）

```
db_init/data/
  README.md                ← 情報源ごとの出所・取得日・各ファイルの意味（git 管理）
  hiroba_qa/               ← hiroba_qa.dvc
    category.csv
    exportjson_withguid.json
    question_altered.csv
    small/                 ← 開発・検証用の縮小版（ファイル名から _small を外す）
      exportjson_withguid.json
      question_altered.csv
  troubleshooting/         ← troubleshooting.dvc
    trouble_shooting.html
    trouble_shooting_netauth.html
```

- 情報源ごとにディレクトリを分け、DVC もディレクトリごとに `.dvc` を作る。情報源ごとに改善の履歴とバージョンを追えるようにするためである。
- 広場 QA のファイルは、すでに環境変数（`QA_ORIGINAL_FILE` など。`CSV_DATA_DIR` からの相対パス）で指定しているので、値を `hiroba_qa/...` や `hiroba_qa/small/...` に変えるだけで済む。AWS の既定値（`variables.tf`）は縮小版を指しているが、フル版と縮小版のどちらを既定にするかは移行時に決めて `.env.example` に明記する。
- トラブルシューティングの HTML のパスは `main.py` の `TROUBLESHOOTING_SOURCES` にハードコードされているので、`troubleshooting/` を付ける。DB に保存する `source_key` は変えない。
- Dockerfile の `COPY data /data` と、ADR-0034 の同梱方針は変えない。

### 4. ローカル環境の整理

- DB のデータ置き場を `.local/volumes/knowledge_db/` と `.local/volumes/conversation_db/` にまとめ、`.local/` を git の管理外にする。
- 使われていない `db_nomic/init.sql`、`db_multilingual/`、`db_conversation/init.sql` を削除する。
- `DB_DIR` による切り替え（nomic 768次元 / multilingual 384次元）は、現在の埋め込みモデルと次元の扱いを実装時に確認したうえで廃止する。必要なら埋め込み次元の設定に置き換える。

### 5. 移行手順（1回のリリース）

1. **前提の確認**: destroy する前の全データエクスポート（ADR-0047）のダンプが手元にあること。テーブル名は変わらないので、ダンプの中身を変換する必要はなく、ファイル名を `chatbot.sql`→`knowledge.sql` に変えるだけで済む（ダンプにはロールや OWNER の記述が含まれないことを確認済み）。
2. **コードの一括変更**: 対応表のとおりに次をまとめて変更し、同じリリースに含める。
   - ディレクトリの移動（`git mv`）
   - 識別子の置換
   - データの再配置
   - 既存テスト（`terraform/deploy/tests/`・`db_init/tests/`・`web_backend` など）の修正
3. **ローカル**: docker-compose を停止し、古いボリューム（`db_nomic/data`・`db_conversation/data`）を退避または破棄する。新しい構成で起動し、`db_init` でマイグレーションとシードを行い、ダンプを再インポートする。
4. **AWS**: `apply-database` → `apply-app` → `seed` → `import-data` の順に、新しい名前で作り直す。Secrets は `name_prefix` で作られるので、削除待ち期間中の古いシークレットと名前が衝突することはない。
5. **ドキュメント**: `README.md`・`terraform/README.md`・`.env.example`・`terraform/.env.example` を更新する。エクスポート画面の文言を変えるので、CLAUDE.md の規約に従い `docs/screen_transition/画面遷移図.md` の該当説明とスクリーンショットも同じ変更の中で更新する。過去の ADR と要件定義書は**書き換えない**（当時の記録として残す）。ADR 一覧の冒頭に、名前の対応表の所在を示す1行を追記する。

## 検討した代替案

- **ADR-0069 / ADR-0077 の方針を続け、名前を変えない**
  - 変更はゼロで済む。
  - しかし、名前が4つ混在している状態が続き、今後 DVC・評価ループ・新しい情報源を追加するたびに混乱が増える。
  - 環境を destroy したため作り直しのコストがほぼゼロになり、名前を変えない利点は小さくなった。不採用。
- **`db_hiroba_qa_init` だけ名前を変え、`chatbot_*` の識別子は据え置く**
  - 変更範囲を半分程度にできる。
  - しかし、ロール・シークレット・環境変数の名前を変えられるのは AWS の作り直しと同時のときが最も安く、今回を逃すと次の機会は RDS の置換を伴う。
  - 部分的な整理では「chatbot＝ナレッジ DB」という読み替えが残るため、不採用。
- **実DB名も変える（例: `knowledge_base`）**
  - 語彙はそろう。
  - しかし、名前を変えるのは ADR-0069・ADR-0077 に続いて3度目になる。今の名前は実態とずれておらず、ダンプや手順書への影響に見合う利点がない。不採用。
- **サービス名を `db_ops` などにする**
  - マイグレーション以外の運用（インポート・アドホック SQL）も担っていることは表せる。
  - しかし、既にある terraform モジュール `db-init-task` とコンテナ名 `chatbot_db_init` に合わせる方が、変更点と読み替えが少ない。`db_init` を採用した。

## 結果・影響

- 識別子の語彙が「プロジェクト＝`chatbot`、ナレッジ DB＝`knowledge`、会話 DB＝`conversation`、広場由来＝`hiroba`」にそろい、名前から指している対象が分かるようになる。
- docs 以外で約30ファイル、テストを含めて一括で変更する。置換漏れは移行後に次の grep で確認する（いずれも0件であること）。
  - `db_hiroba_qa_init`・`db-hiroba-qa-init`・`db_support_knowledge`
  - ナレッジ DB を指す `chatbot_app` / `chatbot_migrator` / `chatbot_export_reader` / `CHATBOT_`
- ADR-0097（DVC）は、本ADRのディレクトリ構成（`db_init/data/hiroba_qa.dvc`・`db_init/data/troubleshooting.dvc`）を前提に実装する。DVC を導入する前にディレクトリを整理しておくので、DVC の履歴に移動が混ざらない。
- 過去の ADR・要件定義書・実装計画書には古い名前が残る（約77ファイル）。履歴として書き換えず、本ADRの対応表を読み替えの基準にする。
- ローカル DB のボリュームを作り直すため、開発者は手元の DB をダンプから復元する必要がある。
