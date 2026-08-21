# ADR-0040: デプロイオーケストレーションのコンテナ内Python化と設定の単一.env集約

- ステータス: Accepted
- 日付: 2026-08-19
- 関連: ADR-0027, ADR-0028, ADR-0036, ADR-0037, ADR-0038, ADR-0039, `docs/requirement/202608180957_Terraform構成再編要件定義書.md`
- 本ADRは、ADR-0038（`.env`→`TF_VAR_*`供給）・ADR-0039（2層構成・スクリプト群）で定めた「Windows PowerShell 5.1互換の`.ps1`＋`.bat`ダブルクリック」という**実行系の技術選定**を改訂する。state 2層構成・依存方向・stateバケット等（ADR-0039）、既存VPC参照（ADR-0036）、DB永続化（ADR-0037）といった**構成方針は一切変更しない**。ADR-0028（`terraform.tfvars`による環境固有設定）は本ADRにより`.env`一元化へ改訂される。

## コンテキスト

ADR-0039 の2層構成を実際に検証環境へデプロイする過程で、`terraform/scripts/*.ps1`（Windows PowerShell 5.1）による実行系が、日本語Windows環境（システムANSIコードページ=CP932）固有の不具合を連続して顕在化させた。

1. **native stderr の終了エラー昇格**: `$ErrorActionPreference='Stop'`下で、ネイティブコマンド（docker/aws）が stderr に出力するだけで `NativeCommandError` に昇格しスクリプトが停止（`docker info` の警告、`aws s3api` の NotFound で発生）。`*> $null` でも回避不可で、EAP を一時的に下げるラッパ（`Invoke-NativeQuiet`）が必要になった。
2. **`Get-Content` の既定エンコーディング**: UTF-8（BOM無し）の`.env`/`.tfvars`をCP932で誤デコードし、日本語コメント末尾が改行を巻き込んで次行の`key = value`を取りこぼす（`vpc_id`未設定エラーの真因）。`-Encoding UTF8`必須。
3. **`-target=module.ecr` の引数分割**: PowerShell 5.1 が未クォートの`-target=module.ecr`を`-target=module`と`.ecr`に分割し、`Error: Invalid target "module"`。
4. **ネイティブ→ネイティブのパイプ破損**: `aws ecr get-login-password | docker login --password-stdin`のパイプがトークンを再エンコード（末尾CRLF付加等）し、`docker login`がECRで`400 Bad Request`。`cmd /c`への委譲が必要になった。

いずれも**発生源はホストのシェル（PowerShell 5.1 + CP932）**であり、個別に修正はしたものの、同種の落とし穴が今後も新しい箇所で再発しうる。加えて、設定が`scripts/.env`（共通値）と各構成の`terraform.tfvars`（構成固有値）に**分散**しており、共有変数（埋め込みモデルID・次元）の二重管理という別課題もある。

要件定義書 §11.1 は当初「Windows PowerShell 5.1互換・`.bat`ダブルクリック起動を維持する」としていたが、これは「実行系の技術」への制約であり、上記のクラスの不具合を根本的には解消しない。

検討した選択肢:

1. **コンテナ内Python化**: 実行系を Linux コンテナ内の Python（subprocessのリスト引数 + boto3）へ移す。`.bat`は`docker run`の薄いラッパとして維持。
2. **PowerShell 7 (pwsh) 化**: 既存`.ps1`をほぼ流用しつつ UTF-8 既定・引数/パイプ改善で4不具合を解消。ただし pwsh の追加インストールが必要。
3. **ホスト直Python化**: `.bat`が`python`を直接呼ぶ。コンテナ不要だが、ホストに Python/terraform/aws CLI が必要。
4. **現状維持（PS 5.1継続）**: 既知4件は個別修正済みだが、5.1固有の落とし穴は今後も個別対処。

あわせて、設定の一元化（`terraform.tfvars`廃止・単一`.env`化）を検討した。

## 決定

**実行系を「Dockerコンテナ内の Python オーケストレータ」に置き換える（案1を採用）。あわせて全設定を単一の`terraform/.env`に集約し、`terraform.tfvars`を廃止する。**

- **実行主体**: `terraform/deploy/`に Python パッケージ（`src/`。コンソールスクリプト名は `deploy`）と`Dockerfile`を置く。イメージには python 3.11 + terraform（ホストと同じ版にピン）+ docker CLI（client）を同梱する。ホストは Docker Desktop だけあればよく、terraform/aws CLI のホスト導入は不要。
- **`.bat`ダブルクリックUXは維持**: 各`terraform/*.bat`は`terraform/deploy/run.bat`経由で「イメージ未作成なら build → `docker run`」を行う薄いラッパにする。要件定義書 §11.1 の「`.bat`ダブルクリック起動を維持する」は継続充足する。「Windows PowerShell 5.1互換を維持する」の部分は本ADRで撤回する（実行系はコンテナ内Pythonとする）。
- **不具合の構造的回避**: 外部コマンドは全て`subprocess`のリスト引数（`shell=False`）で実行（→ 不具合3）、ファイルI/Oは`encoding="utf-8"`固定かつLinux環境（→ 不具合2）、ECRログインは boto3 の`get_authorization_token`を用いパイプを排除（→ 不具合4）、終了判定は戻り値で行い stderr を例外化しない（→ 不具合1）。
- **Docker-out-of-Docker**: コンテナから ECR への build/push が必要なため、ホストの Docker デーモンをソケット共有で駆動する。本イメージは Linux コンテナのため `-v /var/run/docker.sock:/var/run/docker.sock` を bind する（Docker Desktop が Linux コンテナへこのソケットを提供する。`//./pipe/docker_engine` は Windows コンテナ用で Linux コンテナでは接続不可）。build コンテキストは docker CLI がコンテナ内からデーモンへストリーム送信するため、リポジトリを`/work`にマウントしていればパス問題は生じない。
- **設定の単一`.env`集約**: `AWS_*`/`STATE_*`（認証・state）に加え、terraform 変数を`TF_VAR_*`として同じ`.env`に記述する。`deploy`が`.env`を読み、`AWS_*`/`STATE_*`はマッピングし、`TF_VAR_*`は verbatim で`os.environ`へ渡す。terraform は未宣言変数の`TF_VAR_*`を無視するため、database/app 両構成の変数を1ファイルに置いても各構成は自分の変数だけを拾う（superset で安全）。共有変数（`bedrock_embedding_model_id`/`embedding_vector_dim`/`image_tag`）は1エントリに統合し drift を防ぐ（ADR-0038 の思想の延長）。
- **実行時上書き**: `deletion_protection`/`skip_final_snapshot`（destroy-database の2段階）と`knowledge_mcp_desired_count`（seed ゲート）は`.env`に通常値を置き、コマンドが`-var`で上書きする（`-var`は`TF_VAR_`より優先）。
- **保持する振る舞い**: 前提チェック + アカウント安全ガード、構成別の必須変数検証、state バケット冪等作成、ECR 先行 apply→login→build/push、seed の run-task ポーリング（STOPPED待機→`exitCode==0`）、seed ゲート（0→seed→1）、destroy 順序ガード + タイプ確認 + RDS 2段階破棄——いずれも Python 側に等価移植する。旧`load-env.ps1`（手動 apply 用の環境設定）は`deploy shell`（環境設定済みでコンテナ内 bash に入る）で代替する。

## 検討した代替案

- **案2（PowerShell 7）**: 移行工数は最小で4不具合も解消するが、5.1（Windows同梱）と異なり pwsh の追加インストールが要る。かつ実行系がPowerShellに留まり、リポジトリ標準言語（アプリ側5パッケージが Python 3.11）とも乖離するため不採用。
- **案3（ホスト直Python）**: コンテナ関連の考慮（ソケット共有・クロスOS init）が不要で軽量だが、ホストに Python/terraform/aws CLI の導入・版管理が必要で再現性が案1に劣る。将来CI（Linux）や別マシンへの展開も案1の方が容易なため、再現性を優先して不採用。
- **案4（現状維持）**: 追加コストは無いが、5.1×CP932 固有の落とし穴を今後も個別対処し続けることになり、根本解決にならないため不採用。

## 結果・影響

- ADR-0028 の「環境固有設定を`terraform.tfvars`で管理する」は、本ADRにより「単一`.env`（`TF_VAR_*`）へ集約する」に改訂される。旧`terraform.tfvars`は`*.tfvars.migrated`へ退避し（値は`.env`へ移行済み・Git管理外）、`terraform.tfvars.example`は`.env.example`へ統合して廃止する。
- ADR-0038 の「共通値を`.env`経由の`TF_VAR_*`で供給する」方針は維持しつつ、対象を共通値だけでなく**全構成変数**へ拡張する。手動 apply の前提だった`load-env.ps1`の dot-source は不要になり、`deploy shell`に置き換わる。
- 要件定義書 §11.1 の「Windows PowerShell 5.1互換を維持する」を「デプロイ実行系はコンテナ内 Python とし、`.bat`ダブルクリック起動を維持する」に改訂する。
- 実行に terraform をコンテナ（Linux）内で行うため、`.terraform.lock.hcl`に`linux_amd64`のプロバイダハッシュが必要になる（`terraform providers lock -platform=linux_amd64 -platform=windows_amd64`で両対応にする）。以後ホストで直接 terraform を実行しない前提とし、直接実行が必要な場合は`deploy shell`から行う。
- 旧`terraform/scripts/*.ps1`はパリティ確認後に撤去する（移行期間中はロールバック用に残置可）。
- Windows の Docker ソケットマウントには Docker Desktop 側の許可が必要な場合がある。bootstrap のローカル state は`/work`マウントでホストに永続化され、かつ state バケットは`head-bucket`で冪等判定するため、ローカル state が失われても既存バケットは再作成されない。
