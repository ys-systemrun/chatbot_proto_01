# terraform/deploy/src — deploy コマンドの Python パッケージ

`deploy` コンソールスクリプトの実装（ADR-0040）。外部コマンドはすべて subprocess のリスト引数で呼び、AWS 操作は boto3 で行うことで、PowerShell 5.1 / CP932 由来の不具合（引数分割・パイプ破損・誤デコード）を避ける。
`terraform/deploy/Dockerfile` でイメージに pip install され、`run.bat` 経由で `-w /work/terraform` を作業ディレクトリとして実行される。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ定義とバージョン（旧 ps1 からの置き換えの経緯を docstring に記載） |
| [`__main__.py`](__main__.py) | CLI エントリポイント。argparse でサブコマンド（bootstrap / apply-datastore / dvc / apply-database / apply-app / apply-all / seed / migrate / import-data / query / export-data / destroy-app / destroy-database / destroy-all / shell 等）を `commands` の各関数へ振り分け、`DeployError` を捕捉して exit 1 |
| [`commands.py`](commands.py) | 各コマンドの本体（旧 *.ps1 と対応）。前提チェック、構成ごとの init/apply/destroy、イメージ build/push、シード完了ゲート、db_init run-task（seed / migrate / import / query / export）、退避と一括破棄・再開、サービス安定待機と失敗時の診断表示 |
| [`config.py`](config.py) | 単一の `terraform/.env` を読み込み、`AWS_*` / `STATE_*` を環境変数・`TF_VAR_*` へ反映し、`TF_VAR_*` は値そのままで素通しする（ADR-0038 / ADR-0040） |
| [`aws.py`](aws.py) | boto3 による AWS 操作（アカウント照合、S3、ECR ログイン、run-task 起動と停止待ち、CloudWatch Logs 取得、ECS サービスの desired count 変更・安定待機・診断）。boto3 は関数内で遅延 import |
| [`tf.py`](tf.py) | terraform 呼び出し（backend 付き init / ローカル init / apply / destroy / state list / output） |
| [`dockercli.py`](dockercli.py) | docker CLI 呼び出し（ECR への `--password-stdin` ログイン、build と push）。ホストの Docker デーモンをソケット共有で駆動（DooD） |
| [`kbdata.py`](kbdata.py) | DVC 管理のシード元データを db_init イメージのビルド前に `dvc pull` し、`.dvc` との一致を検証して情報源ごとの md5 と commit を「版」として返す（ADR-0097） |
| [`gitinfo.py`](gitinfo.py) | デプロイするコードの git commit と未コミット変更の有無（`GIT_COMMIT` / `GIT_DIRTY`）を取得（ADR-0099 §1） |
| [`tfvars.py`](tfvars.py) | 構成（database / app）ごとの必須 `TF_VAR_*` が環境変数に非空で存在するかの検査 |
| [`paths.py`](paths.py) | terraform ルート（cwd または `TERRAFORM_ROOT`）・リポジトリルート・各構成ディレクトリ・ナレッジデータの場所の解決 |
| [`proc.py`](proc.py) | 外部コマンド実行ヘルパ（`shell=False`・UTF-8 固定の run / capture） |
| [`prompts.py`](prompts.py) | 対話確認（y/N 確認と、破棄系の文字列タイプ確認。後者は `--yes` で省略不可） |
| [`log.py`](log.py) | 色付きコンソール出力（step / info / ok / warn / error） |
| [`errors.py`](errors.py) | 共通例外（`DeployError` と、サービス安定待機失敗の `ServicesNotStable`） |
