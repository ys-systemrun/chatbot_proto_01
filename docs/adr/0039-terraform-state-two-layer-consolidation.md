# ADR-0039: Terraform state 3層構成から「database構成/app構成」2層構成への統合

- ステータス: Accepted
- 日付: 2026-08-18
- 関連: ADR-0027, ADR-0036, ADR-0037, ADR-0038, `docs/requirement/202608180957_Terraform構成再編要件定義書.md`
- 本ADRは ADR-0037 の「network / database / app の3層state分割」という決定を、運用実績を踏まえて2層に再編するものであり、ADR-0037を破棄するのではなく**改訂（Superseded partially）**する。ADR-0036（既存VPC参照）・ADR-0038（`.env`経由の共通変数供給）の決定自体は維持する。

## コンテキスト

ADR-0036〜0038により、`terraform/`配下は次の3つの独立したTerraform root（各々別state、ADR-0027のS3バックエンド方式）に分割されている。

1. `envs/verify-network`（ネットワーク層）: 既存VPC/サブネット参照 + セキュリティグループ + VPCエンドポイント
2. `envs/verify-database`（DB層）: RDS(pgvector) + DBサブネットグループ + `DATABASE_URL`シークレット。永続化運用（`deletion_protection=true`）で、通常の`destroy`運用の対象外
3. `envs/verify`（アプリ層）: ECR + ECS Fargateクラスタ + 3常駐サービス（`knowledge_mcp`/`tag_selector_mcp`/`agent_invitro`） + `db_hiroba_qa_init`のRun Taskタスク定義 + MCP Inspector検証タスク + Bedrock予算アラート

この3層分割は、ADR-0037が課題としたリスク（RDSを含めた誤destroyの防止、アプリ層とDB層の変更頻度の違いの分離）には対応できているが、運用してみると次の点で「構成が理解しづらい」という新たな課題が生じている。

- 3つのrootディレクトリ（`verify-network` / `verify-database` / `verify`）が、それぞれどのリソースを持つのか、`terraform_remote_state`でどの層がどの層を参照するのかという依存関係（network ← database ← app）を把握しないと、変更したいリソースがどのディレクトリにあるか即座に判断できない。
- `verify-network`と`verify-database`はいずれも「ほぼ単独では意味を持たず、RDSまたはRDSシード処理のための前提リソース」という位置づけが近く、実務上は常にセットで扱われる（`deploy.ps1`でもnetwork→database→appの順に連続してapplyしている）。3層に分ける実益（層ごとに担当・権限を分ける等）は、少なくとも現状の検証環境ではまだ顕在化していない。
- `db_hiroba_qa_init`（シード用ECSタスク定義）は「RDSにデータを投入するための専用リソース」という性質上、DB層と一体で管理する方が理解しやすいが、現状はアプリ層（`envs/verify`）に置かれており、「DB関連リソースがDB層とアプリ層に分散している」状態になっている。

検討した選択肢は次の3案。

1. **2層に統合する**: 「RDS本体 + ネットワーク基盤 + シード用ECS周辺リソース」をdatabase構成、「アプリ側ECS常駐サービス周辺リソース」をapp構成として、2つの独立Terraform root（2 state）に再編する。
2. **3層構成を維持しつつドキュメント・命名を改善する**: state分割自体は変更せず、README・ディレクトリ名やREADMEの説明図を改善して理解しやすくするに留める。
3. **単一state構成へ戻す（ADR-0037以前の状態に戻す）**: 3層・2層のいずれの分割もやめ、単一rootに統合する。

## 決定

**「RDS・ネットワーク基盤・シード用ECS周辺リソース」をdatabase構成、「アプリケーション側ECS常駐サービス周辺リソース」をapp構成とする2層構成に再編する（案1を採用）。**

- ネットワーク層（ADR-0036）とDB層（ADR-0037）を1つのTerraform root（database構成、ディレクトリ: `terraform/main/database`）に統合する。database構成は次を含む: 既存VPC/サブネットの参照とセキュリティグループ・VPCエンドポイントの作成（旧`verify-network`）、RDS本体・DBサブネットグループ・`DATABASE_URL`シークレット（旧`verify-database`）、`db_hiroba_qa_init`のシード用ECSタスク定義（旧`verify`から移設）、シードに使うイメージ用ECRリポジトリ1件（旧`verify`の`module.ecr`から分離）。
- アプリケーション側ECS常駐サービス周辺リソースを、引き続き独立したTerraform root（app構成、ディレクトリ: `terraform/main/app`）で管理する。app構成は、Service Connect名前空間・ECS Fargateクラスタ・3常駐サービス（`knowledge_mcp`/`tag_selector_mcp`/`agent_invitro`）・MCP Inspector検証タスク定義・Bedrock予算アラート・残り4リポジトリ分のECRを含む。
- `terraform/envs/`という現行のトップレベルディレクトリ名は`terraform/main/`に改称する。配下の2ディレクトリはそれぞれ`database`・`app`という名称に確定する。
- app構成は、database構成の出力（VPC/サブネットID、各サービス用セキュリティグループID、`db_url_secret_arn`等）を`terraform_remote_state`で参照する一方向の依存とする（database構成はapp構成を参照しない）。これはADR-0037が採用した「network ← database ← app」の参照方式を踏襲するもので、3層が2層になるだけで参照の仕組み自体（S3バックエンド + `terraform_remote_state`、ADR-0027）は変更しない。
- 「DB実体は永続化し、通常のdestroy運用の対象外とする」というADR-0037の中核方針は維持する。ただし対象範囲は「DB層のみ」から「database構成全体（ネットワーク・RDS・シードタスク定義）」に広がる。通常のコスト管理目的のdestroyはapp構成のみを対象とし、database構成（RDSを含む）の破棄は、旧`destroy-database.bat`と同様に、明示的な確認を要する別操作として維持する。
- Terraform state用S3バケット名は`chatbot-invitro-terraform-state-349131272460-us-east-1-an`に確定する（`bootstrap/`で作成）。database構成・app構成とも同一バケット内の別パス（`database/state.tfstate` / `app/state.tfstate`）に配置する。
- 共通設定値（`aws_region`/`aws_account_id`/`name_prefix`/`state_bucket`）を`scripts/.env`から`TF_VAR_*`として供給する方式（ADR-0038）は、対象rootが3つから2つに減る点を除き変更しない。
- 具体的なディレクトリ構成・スクリプト要件・移行方針は`docs/requirement/202608180957_Terraform構成再編要件定義書.md`に整理する。本ADRは「2層に再編する」という構成方針、ディレクトリ名、stateバケット・パスの決定を扱う。

## 検討した代替案

- **案2（3層維持 + ドキュメント改善）**: 追加のstate移行やスクリプト改修が不要で最も低コストだが、コンテキストで述べた「実務上ネットワーク層とDB層は常にセットで扱われている」「シード用リソースがDB層とアプリ層に分散している」という構造的な分かりにくさそのものは解消されない。ドキュメントを改善しても、ディレクトリ数・stateファイル数が減るわけではないため、今回は不採用とした。
- **案3（単一state構成へ戻す）**: ディレクトリ・state数が最小になり最も理解しやすい反面、ADR-0037が採用した「RDSを誤ってdestroyしない」という安全性を単一state内の`lifecycle`/target運用だけで担保する必要があり、ADR-0037の検討時に不採用とした案2（単一state + prevent_destroy/target運用）と同じ弱点を再び抱える。RDSの永続化とアプリ層の頻繁なapply/destroyという運用実態（ADR-0037のコンテキスト参照）を踏まえ、少なくとも「永続化したいdatabase構成」と「頻繁に変更するapp構成」の2つは分けておく方が安全側に倒せるため不採用とした。

## 結果・影響

- ADR-0037の「3層（network/database/app）に分割する」という決定内容は、本ADRにより「2層（database構成/app構成）に統合する」へ改訂される。ADR-0037のうち「DB実体を永続化し通常destroy対象から除外する」という中核方針、ADR-0036の「既存VPC/サブネットを新規作成せずdata参照する」という方針、ADR-0038の「共通値を`.env`経由のTF_VAR_*で供給する」という方針は、いずれも変更なく本構成に引き継がれる。3つのADRには本ADRへの参照を追記する。
- `terraform/`配下のディレクトリ構成が再編されるため、既存の`envs/verify-network`・`envs/verify-database`・`envs/verify`は廃止し、新たに`terraform/main/database`・`terraform/main/app`の2ディレクトリを作成し直す（詳細は要件定義書）。`deploy.bat`/`destroy.bat`/`destroy-database.bat`および対応する`.ps1`群も、`apply-database`/`apply-app`/`apply-all`/`destroy-database`/`destroy-app`/`seed`という2層構成向けの構成に再設計が必要になる（要件定義書で機能要件を整理し、実装は別途の実装フェーズで行う）。
- 2026-08-18時点で確認した結果、AWS上への実デプロイ・S3上の旧state（`verify-network.tfstate`等）はいずれも作成されていない。そのため今回の切り替えでは、state移行やRDS等の実リソース保全を考慮した手順は不要であり、既存の`terraform/`配下を単純に削除して新構成を作成すればよい（要件定義書13章）。将来、本ADRの構成が実際にAWS上へデプロイされた後に再度同様の再編を行う場合は、この限りでない点に留意する。
- database構成とapp構成の依存が一方向（database→appの出力参照のみ）である点は維持されるため、apply順序（database→app）に関する運用上の制約はADR-0037時点から本質的に変わらない。一方、destroy順序（app→databaseの逆順が必須）は、ネットワーク層がdatabase構成に統合されたことにより「app構成のリソースが存在する状態でdatabase構成のセキュリティグループ/サブネット参照を破棄しようとして失敗する」というエラーモードが新たに顕在化しうる点に注意が必要。運用手順・スクリプト側での明記が必要（要件定義書で規定）。
- モジュール名`modules/database`（RDSリソース定義）とTerraform root名`main/database`（database構成）が同名になる点は、要件定義書15章オープンイシュー#2として残し、実装フェーズ着手前に混同のリスクを再確認する。
