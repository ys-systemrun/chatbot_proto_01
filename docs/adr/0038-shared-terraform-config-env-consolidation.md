# ADR-0038: 複数state層にまたがる共通設定値の集約方式（`.env`からのTF_VAR_*環境変数エクスポート）

- ステータス: Accepted（ADR-0040 で対象を全構成変数へ拡張）
- 日付: 2026-08-17
- 関連: ADR-0027, ADR-0028, ADR-0036, ADR-0037, ADR-0040
- **注記**: 本ADRの「`.env`→`TF_VAR_*`供給」は当初 `aws_region`/`aws_account_id`/`name_prefix`/`state_bucket` 等の共通値のみが対象だったが、ADR-0040 により**全構成変数**（旧 `terraform.tfvars` 相当）へ拡張された。手動 apply 前の `load-env.ps1` dot-source は不要になり、`deploy shell` に置き換わる。

## コンテキスト

ADR-0036・ADR-0037により、Terraform構成は`envs/verify-network`（ネットワーク層）・`envs/verify-database`（DB層）・`envs/verify`（アプリケーション層）の3つの独立したroot（それぞれ別state）に分割された。実装の結果、`aws_region`・`name_prefix`が3層すべての`terraform.tfvars`に個別に記述され、`aws_account_id`は`envs/verify/terraform.tfvars`と`scripts/.env`（`AWS_ACCOUNT_ID`）の両方に、`state_bucket`は`envs/verify-database`・`envs/verify`の2層のtfvarsにそれぞれ現れる状態になっている。

この重複により、値を変更する際に複数ファイルを揃えて更新する必要があり、更新漏れによる層間の設定不一致（例えばあるレイヤーだけ`name_prefix`が古いままになり、タグやリソース名が層間で食い違う）に気づきにくいという運用上の課題が生じている。ADR-0027・ADR-0037で決めた「stateはS3バックエンドで層ごとに分離する」という方針自体は維持しつつ、**stateの分離とtfvarsの重複は別問題であり、後者だけを解消したい**というのが本ADRの動機である。

検討した選択肢は次の3案。

1. **共通値を`scripts/.env`に集約し、環境変数（`TF_VAR_*`）としてエクスポートする**: 既存の`scripts/.env`（`common.ps1`の`Import-Config`がAWS認証情報・`STATE_BUCKET`を読み込みexportしている仕組み、ADR-0028関連）を拡張し、`aws_region`・`aws_account_id`・`name_prefix`・`state_bucket`についても`TF_VAR_aws_region`等の環境変数としてexportする。Terraformは`TF_VAR_<変数名>`という環境変数を、`-var`や`terraform.tfvars`が指定されていない場合の入力値として自動的に認識する。
2. **層横断の共有tfvarsファイル（`common.tfvars`等）を1つ用意し、各層に`-var-file`または`*.auto.tfvars`配置で読み込ませる**: Terraformのvarファイルの仕組みだけで完結させる方式。
3. **現状維持（各層のtfvarsに個別記述）**: 追加の仕組みが不要な反面、コンテキストで述べた重複・更新漏れのリスクをそのまま残す。

## 決定

**共通設定値を`scripts/.env`に集約し、`TF_VAR_*`環境変数として各層のTerraform実行に供給する（案1を採用）。**

- `aws_region`・`aws_account_id`・`name_prefix`・`state_bucket`（DB層・アプリケーション層がネットワーク層・DB層のstateを`terraform_remote_state`で参照する際に使う値）を、共通設定値として`scripts/.env`に一本化する。`AWS_REGION`・`AWS_ACCOUNT_ID`・`NAME_PREFIX`・`STATE_BUCKET`のキーで保持する。
- `scripts/common.ps1`の`Import-Config`関数を拡張し、これらの値を読み込んだ上で`$env:TF_VAR_aws_region`・`$env:TF_VAR_aws_account_id`・`$env:TF_VAR_name_prefix`・`$env:TF_VAR_state_bucket`としてexportする。`deploy.ps1`・`destroy.ps1`・`destroy-database.ps1`は、いずれも`common.ps1`を`dot-source`して`Import-Config`を呼んでいるため、スクリプト経由の実行では追加の変更なしにこの仕組みが効く。
- 各層（`envs/verify-network`・`envs/verify-database`・`envs/verify`）の`terraform.tfvars`・`terraform.tfvars.example`から、`aws_region`・`name_prefix`（該当する場合は`aws_account_id`・`state_bucket`）のキー自体を削除する。各層のtfvarsには、その層固有の値（既存VPC/サブネットID、RDSエンジンバージョン、BedrockモデルID等）のみを残す。
- README記載の「手動`terraform apply`」手順（`deploy.bat`を使わず、各層ディレクトリで直接`terraform apply`を実行する運用）も継続してサポートする方針のため、`scripts/`に`Import-Config`のみを呼び出す軽量なエントリーポイント（例: `scripts/load-env.ps1`）を用意し、開発者がシェルセッションの最初に一度これを実行（dot-source）すれば、以降どの層のディレクトリで`terraform apply`を直接実行してもTF_VAR_*が有効な状態になる運用とする。具体的なスクリプトの実装は実装フェーズで行う。

## 検討した代替案

- **案2（共有tfvarsファイル + auto.tfvars/`-var-file`）**: Terraformのネイティブな仕組みだけで完結し、シェル環境やPowerShellスクリプトに依存しない点は利点だが、`.gitignore`対象の設定ファイルという概念を`scripts/.env`（ADR-0028）と`common.tfvars`（本案）の2種類に増やすことになり、「環境固有の値はどこに書くべきか」という判断基準が1つ増えて分かりやすさが下がる。今回は、既に確立している`.env`パターン（ADR-0028、認証情報・`STATE_BUCKET`）を唯一の共通設定源として拡張する方が一貫性が高いと判断し、不採用とした。将来、共有値の種類・層の数が増えて`.env`方式の限界（環境変数の一覧管理のしづらさ等）が顕在化した場合は、本ADRを見直し案2を再検討する。
- **案3（現状維持）**: 追加実装が不要な点はシンプルだが、コンテキストで述べた重複・更新漏れのリスクを解消できないため不採用とした。

## 結果・影響

- `scripts/common.ps1`の`Import-Config`の実装拡張、各層`terraform.tfvars.example`からの重複キー削除、README（「実行手順」節）への「初回に`load-env.ps1`を実行しておく」手順の追記が実装フェーズで必要になる。
- Terraformの変数値解決の優先順位上、`TF_VAR_*`環境変数は`-var`・`*.auto.tfvars`・`terraform.tfvars`のいずれよりも優先度が低い（変数のデフォルト値よりは優先される）。そのため、各層の`terraform.tfvars`に同名キー（`aws_region`等）が誤って残っていると、`TF_VAR_*`の値は無視されてtfvars側の値が使われてしまう。実装フェーズで各層のtfvars（サンプル・実ファイルの両方）から該当キーを確実に削除し、コメントで「`.env`経由のTF_VAR_*で供給される」旨を明記することで、この落とし穴を防ぐ。
- ADR-0028（`terraform.tfvars`をGit管理外とする方式）自体の決定に変更はないが、「環境固有かつ複数層で共有される値は`.env`（TF_VAR_*経由）に置き、層固有の値のみを各層の`terraform.tfvars`に書く」という役割分担が本ADRにより明確化される。ADR-0028には本ADRへの参照を追記する。
- 手動`terraform apply`によるデバッグ・部分適用（README記載の運用）は、`load-env.ps1`（またはその同等手段）の実行を前提とする運用ルールに変わる。これを踏まえていない状態で層ディレクトリに直接入って`terraform apply`を実行すると、共通変数が未設定のためTerraformが対話的に値の入力を求める（またはCI等の非対話実行では失敗する）点を、README・実装フェーズの周知事項として残す。
