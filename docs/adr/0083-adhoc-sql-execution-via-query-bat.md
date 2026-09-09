# ADR-0083: アドホックSQL実行機能（query.bat / query.sql）の実行方式 — 既存db_hiroba_qa_initタスクの環境変数分岐による再利用、実行前タイプ確認あり

- ステータス: Accepted
- 日付: 2026-09-09
- 関連: ADR-0026, ADR-0036, ADR-0037, ADR-0039, ADR-0040, ADR-0052, ADR-0066, ADR-0075, ADR-0029

## コンテキスト

現状、AWS環境にデプロイしたRDS（chatbot用データベース`db_chatbot_knowledge_base`・conversation用データベース）に対して、運用者が任意のSQL（スキーマ・データの確認SELECT、ピンポイントの手直しUPDATE/DELETE/ALTER等）をその場で実行する手段が用意されていない。

RDSは既存VPCのプライベートサブネットに配置され`publicly_accessible=false`（ADR-0026, `modules/database/main.tf`）であるため、運用者のWindows端末から直接psql等でRDSへ接続することはできない。加えてADR-0040により、実行系は「Dockerコンテナ内のPythonオーケストレータ（`terraform/deploy/`）」に一本化されており、ホストにterraform/aws CLIを導入しない方針（`.bat`ダブルクリック→`docker run`）を継続している。deployコンテナ自体もホストのDockerネットワーク越しに動くだけで、VPC内部への到達経路は持たない。

RDSへ到達できる唯一の実行主体は、database構成のプライベートサブネット・セキュリティグループ内で動くECS Fargateタスク（`db_hiroba_qa_init`、`db_init_task_family`）である。このタスクは既に:

- `DATABASE_URL`（chatbot用, マスターロール）・`CONVERSATION_DB_URL`（conversation用, マスターロール）のSecrets Manager参照を環境変数として受け取っている（`main/database/main.tf`のdb_init_taskモジュール呼び出し）。
- `enable_execute_command=true`で起動される（README「ECS Execは事後有効化不可」の対象）。
- `MIGRATE_ONLY`（ADR-0075）・`IMPORT_MODE`（ADR-0066）という環境変数分岐により、同一イメージ・同一タスク定義のまま複数の起動モードを切り替える前例を既に持つ。

一方、`migrate`・`seed`・`import-data`はいずれも「実行結果を行データとして画面に返す」ことを要求しない設計になっている（`terraform/deploy/src/aws.py`の`wait_task_stopped`・`task_exit_code`は、ECSタスクの`exitCode`のみを確認する）。今回追加したいquery機能は、SELECT結果を画面で確認したいユースケースを含む（ユーザー確認済み）ため、既存の「exitCodeだけ見る」設計をそのまま流用できない。CloudWatch Logs自体は`db_hiroba_qa_init`の全ログ出力先として既に存在する（`aws_cloudwatch_log_group.this`、ロググループ名`/ecs/db-hiroba-qa-init`、ストリームプレフィックス`db-hiroba-qa-init`、`modules/db-init-task/main.tf`）が、`deploy`側はこれを取得・表示する処理をまだ持たない。

ユーザーへの確認により、本機能の要件は次の通り確定した。

1. `query.sql`の用途はSELECT（参照）とUPDATE/DELETE/ALTER等（更新）の両方を想定する。
2. 対象データベース（chatbot / conversation）は実行時に選択可能にする。
3. 実行方式は、既存の`db_hiroba_qa_init`イメージ・既存ECSタスク定義（`db_init_task_family`）の使い回し（新規インフラなし）を採用する。
4. **`query.sql`には破壊的なSQL（DROP/DELETE/TRUNCATE等）が書かれうるため、`query.bat`実行前に確認プロンプトを設ける**（ユーザーは当初「確認なし」を選んだが、検討の過程で「やはり確認を入れてほしい」と方針転換した）。

## 決定

**`db_hiroba_qa_init`に新規モード`QUERY_MODE`を追加し、既存の`db_init_task_family`を環境変数オーバーライドで起動する。SQL本文は`run-task`のcontainer environmentオーバーライドで渡し、実行結果（SELECT結果を含む標準出力）はCloudWatch Logsから`deploy`が取得してコンソールに表示する。実行前には、対象データベース名のタイプ入力による確認（`import-data`と同一パターンの`confirm_typed`）を必須とする。**

1. **`db_hiroba_qa_init`側のモード分岐（`src/main.py`）**: `QUERY_MODE`（真偽値、既存の`IMPORT_MODE`/`MIGRATE_ONLY`と同じ判定方式）を新設する。真の場合、通常のマイグレーション・シード処理には一切分岐せず、次のみを行う。
   - `QUERY_TARGET_DB`（`chatbot` | `conversation` | `both`）で指定されたデータベースへ、対応するマスター接続文字列（`DATABASE_URL` / `CONVERSATION_DB_URL`、いずれも既にタスクへ注入済みのSecrets Manager参照）で接続する。`both`指定時はchatbot→conversationの順に同一SQLを逐次実行し、対象ごとに結果を区切って出力する。
   - `QUERY_SQL`（環境変数オーバーライドで渡されるSQL本文の全文）を1つのトランザクションとして実行する（`connection.autocommit=False`、正常終了時にcommit、例外時はrollbackしてexit非0）。
   - SQL本文はセミコロン区切りで複数文を含みうる。psycopg2はパラメータなしの`execute()`では単純クエリプロトコルを使うため複数文が実行できるが、`cursor.description`（結果セットの有無・列情報）は**最後の文のもののみ**が残る。よって**画面に表示する結果セットは、最終文が返した行のみとする**（途中のSELECT文の結果は表示対象外）。これは実装コストを抑えるためのスコープ限定であり、必要になれば別途拡張する。
   - 最終文が結果セットを持つ場合（`cursor.description is not None`）、ヘッダ行＋各行を単純なテキスト形式（実装フェーズで確定、例: タブ区切り）で標準出力へ出力する。結果セットを持たない場合（UPDATE/DELETE/DDL等）は、影響行数（`cursor.rowcount`）のみを出力する。
   - 例外発生時は、エラー内容を標準出力（またはstderr）に出力した上でexit非0とする。
2. **入力方法（環境変数オーバーライド、S3不使用）**: `terraform/deploy`の新規サブコマンド`query`（`cmd_query`）が、ローカルの`terraform/query.sql`（既定パス、`import-data`の`--chatbot-sql`同様に`--sql-file`で上書き可）を読み込み、その全文を`run_import_task`と同型のcontainer environmentオーバーライド（`{"QUERY_MODE": "true", "QUERY_TARGET_DB": <target>, "QUERY_SQL": <query.sqlの全文>}`）として`run-task`に渡す。S3を新たに介さない（既存の全データインポート用S3バケットは、全消去→上書きという性質の異なる用途のためのものであり、アドホックなquery実行の入出力に転用しない）。
   - **既知の制約**: ECS `RunTask`の`overrides`には環境変数の合計サイズに事実上の上限がある（正確な値は実装フェーズでAWS仕様を要確認）。本機能は「短いアドホックなSQL」を主用途とし、対象を数KB程度までに収める運用を前提とする。より大規模なデータ操作（一括投入・全消去上書き等）は、既存の`import-data`（S3経由）を引き続き使う。
3. **対象データベースの選択**: `deploy query`に`--target {chatbot,conversation,both}`引数を設ける（`import-data`の`--target`と同じ選択肢）。既定値は`chatbot`とする（QA・タグ等の参照・保守が主用途と想定されるため）。`terraform/query.bat`は他の`.bat`と同じく`deploy/run.bat`への薄いラッパとし、引数をそのまま転送する（`query.bat --target conversation`で切り替え可能。ダブルクリックのみの場合は既定の`chatbot`で実行する）。
4. **実行前の確認プロンプト（`confirm_typed`方式、`--yes`バイパスなし）**: `deploy query`は、run-task起動前に次を行う。
   - `query.sql`の内容（全文。長大な場合は先頭N行＋省略表示、実装フェーズで確定）と、選択された`--target`を画面に表示する。
   - 既存の`destroy-app`/`destroy-database`/`import-data`が使う`prompts.confirm_typed`と同一のヘルパー関数を再利用し、対象DB名（`chatbot`/`conversation`、`both`指定時は`both`という固定文字列、等の具体的な入力仕様は実装フェーズで確定）のタイプ入力を要求する。入力が一致しない場合は実行を中止する。
   - `import-data`と同様に**`--yes`による確認スキップは設けない**（`bootstrap`/`apply-*`/`seed`の`--yes`は元々「軽微な確認」のスキップであるのに対し、`import-data`・本コマンドは「破壊的操作になりうる」ため、無人実行用のバイパスを持たない`import-data`と同じ厳格さで扱う）。
5. **ファイル配置とGit管理**: `terraform/query.sql`は運用者が都度書き換えるアドホックな実行内容であり、`terraform/.env`と同様の性質（環境固有・実行内容が流動的）を持つため、`.gitignore`に追加しGit管理外とする（リポジトリには`query.sql.example`をテンプレートとして残すか、READMEに使い方を記載するかは実装フェーズで決める）。`terraform/query.bat`・`terraform/deploy`側の変更（`commands.py`/`aws.py`/`__main__.py`）は他の`.bat`と同じくGit管理対象とする。
6. **結果表示（新規: CloudWatch Logs取得）**: `deploy query`は、既存の`wait_task_stopped`でタスク終了（`STOPPED`）を待った後、当該タスクのログストリーム（`awslogs-stream-prefix`規約により`db-hiroba-qa-init/db-hiroba-qa-init/<タスクID>`、`modules/db-init-task/main.tf`のロググループ`/ecs/db-hiroba-qa-init`）を`logs:GetLogEvents`で取得し、標準出力へそのまま表示する。その後、既存の`task_exit_code`でexitCodeを確認し、非0ならエラー終了として扱う（`migrate`/`seed`と同じ判定パターン）。これは`terraform/deploy/src/aws.py`への新規関数追加（例: `get_task_log_events`）を要する、本ADRで唯一の新規AWS操作である。

## 検討した代替案

- **実行確認プロンプトを設けない（`migrate`/`seed`と同じ無人即実行）**: ユーザーは当初この方式を選んだ。「`query.sql`を書いた本人がその場で実行する」という運用者向けツールの位置づけを踏まえれば実装は単純だが、`query.sql`は`migrate`/`seed`が実行する内容（既知のマイグレーションファイル・冪等シード処理）と異なり**内容が都度変わる自由記述のSQL**であり、DROP/TRUNCATE/DELETE等の破壊的操作を一切の歯止めなく実行できてしまう。検討の結果、ユーザー自身がこのリスクを重く見て方針転換し、`import-data`と同様の確認プロンプトを設けることとした。
- **単純なy/n確認（`confirm_or_exit`）とする**: `apply-all`等が使う軽量な確認方式だが、破壊的操作に対する誤操作防止効果は対象名のタイプ確認（`confirm_typed`）に劣る。`query.sql`の内容を都度確認しないまま「y」を押し続けてしまうリスクがあるため、`import-data`と同じ`confirm_typed`（対象DB名のタイプ入力）を採用した。
- **SSMポートフォワーディングでローカルpsqlから直接接続する**: ECS Exec対応タスク経由でRDSへポートフォワードし、deployコンテナ内（またはホスト）のpsqlからほぼ対話的に接続できる利便性があるが、session-manager-pluginの同梱・ネットワーク経路（コンテナ内ポートフォワード→ホストへのポートマッピング）の新規実装が必要になり、ADR-0040が確立した「既存イメージ・既存タスク定義を環境変数で分岐させる」という一貫した前例から外れる。ユーザーの選好（既存ECS一時タスクの使い回しを推奨・選択）によっても不採用とした。
- **専用の軽量SQL実行タスク（psqlクライアントのみを持つ新規ECSタスク定義・イメージ）を新設する**: 責務は`db_hiroba_qa_init`（マイグレーション・シード責務）から分離できるが、新規Dockerfile・ECRリポジトリ・Terraformリソース（タスク定義・IAMロール・ロググループ）が増える。ADR-0066・ADR-0075が確立した「同一イメージ・環境変数によるモード切替」という設計との一貫性が崩れ、新規インフラを避けたいというユーザーの選好にも反するため不採用とした。
- **SQL本文・結果の受け渡しに既存の全データインポート用S3バケット（`import_data`）を流用する**: 新規IAM権限・Terraformリソースが不要という利点はあるが、当該バケットはADR-0066が定めた「全消去→上書き」バッチの投入ダンプ・退避バックアップ専用の意味づけを持つ。性質の異なるアドホックなquery入出力を同じバケット・プレフィックス設計に混在させると運用上の見通しが悪くなるため、まずは環境変数オーバーライドのみで完結させ、SQL本文が環境変数のサイズ上限を恒常的に超えるようになった時点でS3方式への切り替えを再検討することとした。
- **`query.sql`内の複数文それぞれの結果セットを個別に表示する（`sqlparse`等でステートメント分割）**: より丁寧な表示ができるが、SQL文分割ライブラリの追加依存・実装コストが増す。アドホックな1回実行という主用途では「最終文の結果のみ表示」で十分実用的と判断し、まずは最小スコープを採用した。

## 結果・影響

- `db_hiroba_qa_init/src/main.py`の`main()`に、既存の`IMPORT_MODE`/`MIGRATE_ONLY`分岐と同型の`QUERY_MODE`分岐を1箇所追加する。新規のSQL実行・結果整形ロジック（環境変数`QUERY_SQL`/`QUERY_TARGET_DB`の解釈、トランザクション制御、結果セットのテキスト整形）を追加する。
- `terraform/deploy/src/commands.py`に`cmd_query`を、`src/__main__.py`の`build_parser()`に`query`サブコマンド（`--target`, `--sql-file`）を追加する。`cmd_query`は`prompts.confirm_typed`（`destroy-app`/`destroy-database`/`import-data`が使うものと同一ヘルパー）を呼び出す。
- `terraform/deploy/src/aws.py`に、CloudWatch Logsからタスクのログイベントを取得する新規関数（例: `get_task_log_events`）を追加する。これは本ADRで唯一の新規AWS操作であり、`migrate`/`seed`/`import-data`が持たなかった「タスクの標準出力を運用者の画面へ返す」経路を初めて導入するものである。
- IAM: `terraform/deploy`実行主体（運用者のAWS認証情報, `terraform/.env`の`AWS_ACCESS_KEY_ID`等）に`logs:GetLogEvents`（対象: `/ecs/db-hiroba-qa-init`ロググループ）の権限が必要になる。ECSタスク側（execution role / task role）の権限追加は不要（既存の`DATABASE_URL`/`CONVERSATION_DB_URL`シークレット参照・`ecs:RunTask`権限をそのまま利用できる）。
- 新規Terraformリソース（タスク定義・ECR・IAMロール・S3バケット等）は不要。既存の`db_init_task_family`・database構成のみで完結する。
- `terraform/query.bat`（新設, 他の`.bat`と同型だが、確認プロンプトのため`cmd /k`起動後にコンソール上でのタイプ入力待ちが発生する点が他の無人実行系`.bat`と異なる）・`terraform/query.sql`（新設, 運用者が都度編集、Git管理外に追加）・`terraform/README.md`（コマンド一覧・実行手順への追記）・`.gitignore`（`query.sql`の追加）が実装フェーズの作業として発生する。
- 運用上の制約として、(a) `query.sql`はマスターロール権限で実行されるため、対象データベースの全テーブルに対する任意操作（DROP/TRUNCATE含む）が可能である、(b) 実行前確認は「対象DB名のタイプ入力」であり`query.sql`の内容そのものの妥当性は検証しない（誤った`query.sql`をそのまま実行した場合の被害を防ぐ手段は運用者自身の内容確認に委ねられる）、(c) 複数文中、最終文以外のSELECT結果は画面に表示されない、という3点をREADME等に明記する必要がある。データ喪失リスクを懸念する運用（例: 実行前に既存の全データエクスポート機能（ADR-0046/0047）でバックアップを取る等）は、本ADRの対象外（運用ルールとして別途定める）とする。
- ECS `RunTask`の`overrides`環境変数サイズ上限（実装フェーズで要確認）を超えるような大規模SQLは本機能の対象外とし、既存の`import-data`（S3経由の全消去上書き）を引き続き使う、という使い分けが明文化される。
- CloudWatch Logsは`db_hiroba_qa_init`の全出力（migrate/seed/import-data/query全モード共通）が同一ロググループ・ストリームプレフィックスに集約されるため、実行種別の識別しやすさは引き続きADR-0075が残した課題（Open Issue）と共通する。
