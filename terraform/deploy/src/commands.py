"""各コマンド本体（旧 *.ps1 と 1:1 対応）。"""

from __future__ import annotations

import os
import shutil

from . import aws, config, dockercli, log, paths, proc, prompts, tf, tfvars
from .errors import DeployError


# --- 共通ヘルパ ---------------------------------------------------------------

def _image_tag() -> str:
    return os.environ.get("TF_VAR_image_tag", "").strip() or "latest"


def prerequisites(cfg: config.Config, no_docker: bool = False) -> None:
    """前提ツール・認証の確認（旧 Test-Prerequisites）。aws CLI は不要（boto3 使用）。"""
    log.step("前提ツール・認証の確認")
    tools = ["terraform"] + ([] if no_docker else ["docker"])
    for tool in tools:
        if not shutil.which(tool):
            raise DeployError(f"{tool} が PATH に見つかりません。")
        log.ok(f"{tool} あり")
    if not no_docker:
        if proc.capture_result(["docker", "info"]).returncode != 0:
            raise DeployError(
                "Docker デーモンに接続できません。ホストの Docker Desktop を起動し、"
                "Docker ソケット（/var/run/docker.sock）がコンテナへマウントされているか確認してください。"
            )
        log.ok("Docker デーモン稼働中")
    ident = aws.check_account(cfg.aws_account_id)
    log.ok(f"AWS 認証OK (Account: {ident})")


def ensure_state_bucket(cfg: config.Config) -> None:
    """state バケットが無ければ bootstrap 構成で作成（旧 Confirm-StateBucket, 冪等）。"""
    log.step("Phase 0: Terraform state バケット")
    if aws.bucket_exists(cfg.state_bucket):
        log.ok(f"state バケット既存: {cfg.state_bucket}（bootstrap スキップ）")
        return
    log.info(f"state バケットを作成します: {cfg.state_bucket}")
    d = paths.bootstrap_dir()
    tf.init_local(d)
    tf.apply(
        d,
        variables={"aws_region": cfg.aws_region, "state_bucket_name": cfg.state_bucket},
        what="bootstrap apply",
    )
    log.ok("state バケット作成完了")


def _require_database_applied(cfg: config.Config) -> None:
    if not aws.object_exists(cfg.state_bucket, cfg.state_key_database):
        raise DeployError(
            f"database 構成が未 apply です（s3://{cfg.state_bucket}/{cfg.state_key_database} が見つかりません）。\n"
            "  先に apply-database を実行してください（ADR-0039: database → app の順）。"
        )


def _require_app_applied(cfg: config.Config) -> None:
    if not aws.object_exists(cfg.state_bucket, cfg.state_key_app):
        raise DeployError(
            f"app 構成が未 apply です（s3://{cfg.state_bucket}/{cfg.state_key_app} が見つかりません）。"
            "  先に apply-app を実行してください。"
        )


def _reconcile_agent_after_servers(cluster: str, region: str) -> None:
    """Service Connect のクライアント(agent_invitro)を、サーバ登録後に起動させ直す。

    apply では3サービスが同時作成され、クライアント(agent_invitro)がサーバ(tag_selector_mcp/
    knowledge_mcp)の Service Connect 登録より先に安定してしまうと、そのタスクは相手を名前解決できない
    （httpx: Name or service not known）。サーバ安定を待ってから agent_invitro を強制再デプロイし、
    サーバ登録後に新タスクが起動するようにする。apply 本体は成功済みのため、失敗しても警告に留める。
    """
    try:
        log.step("Service Connect 整合: サーバ安定後に agent_invitro を再デプロイ")
        log.info("tag_selector_mcp / knowledge_mcp の安定を待機...")
        aws.wait_services_stable(cluster, ["tag_selector_mcp", "knowledge_mcp"], region)
        log.info("agent_invitro を強制再デプロイ（サーバ登録後に起動させ名前解決を確実化）")
        aws.force_new_deployment(cluster, "agent_invitro", region)
        aws.wait_services_stable(cluster, ["agent_invitro"], region)
        log.ok("agent_invitro 再デプロイ完了")
    except Exception as exc:  # noqa: BLE001 - 整合処理の失敗で apply 全体を失敗扱いにしない
        log.warn(f"agent_invitro の自動再デプロイに失敗/タイムアウトしました: {exc}")
        log.warn(f"  手動: aws ecs update-service --cluster {cluster} --service agent_invitro --force-new-deployment")


def _info_output(cwd, name: str, label: str) -> None:
    """apply 完了後の情報表示用に output を best-effort で表示する。

    apply 本体は成功しているので、末尾の情報取得が失敗してもコマンド全体を失敗扱いにしない
    （例: output 定義が state 未反映のケースでも警告に留める）。
    """
    try:
        log.info(f"{label}: {tf.output_raw(cwd, name)}")
    except DeployError:
        log.warn(f"output '{name}' を取得できませんでした（apply 自体は完了しています）。")


# --- コマンド -----------------------------------------------------------------

def cmd_bootstrap(assume_yes: bool = False) -> None:
    cfg = config.load_config()
    prerequisites(cfg, no_docker=True)  # バケット作成に Docker は不要
    log.info(f"state_bucket={cfg.state_bucket} / region={cfg.aws_region}")
    prompts.confirm_or_exit(
        f"AWS 上に Terraform state 用 S3 バケット '{cfg.state_bucket}' を作成します（リージョン: {cfg.aws_region}）。",
        assume_yes,
    )
    ensure_state_bucket(cfg)
    log.info("次: terraform 変数（TF_VAR_*）を terraform/.env に記入し、apply-database（または apply-all）を実行します。")


def cmd_apply_database(assume_yes: bool = False) -> None:
    cfg = config.load_config()
    prerequisites(cfg)
    tfvars.validate("database")
    d = paths.database_dir()
    image_tag = _image_tag()
    log.info(f"region={cfg.aws_region} / image_tag={image_tag} / state_bucket={cfg.state_bucket} / key={cfg.state_key_database}")
    prompts.confirm_or_exit(
        f"AWS 上に SG/VPCエンドポイント/RDS 等の課金リソースを作成します（リージョン: {cfg.aws_region}）。",
        assume_yes,
    )
    ensure_state_bucket(cfg)

    log.step("database 構成 init（S3 バックエンド）")
    tf.init_backend(d, cfg.state_bucket, cfg.aws_region, cfg.state_key_database)

    log.step("ECR リポジトリ作成（db-hiroba-qa-init）")
    tf.apply(d, targets=["module.ecr"], what="ECR apply")
    repos = tf.output_json(d, "ecr_repository_urls")
    registry = repos["db-hiroba-qa-init"].split("/")[0]

    log.step("Docker イメージ build / push（db-hiroba-qa-init）")
    log.info(f"ECR ログイン: {registry}")
    dockercli.login(registry, cfg.aws_region)
    image = f"{repos['db-hiroba-qa-init']}:{image_tag}"
    dockercli.build_and_push(paths.repo_root() / "db_hiroba_qa_init", image, "db_hiroba_qa_init", "db-hiroba-qa-init")
    log.ok("シード用イメージ push 完了")

    log.step("database 構成 apply（RDS / ネットワーク / シードタスク定義）")
    tf.apply(d, what="database apply")

    log.step("database 構成 apply 完了")
    _info_output(d, "rds_endpoint", "RDS    ")
    _info_output(d, "db_name", "DB name")
    log.info("次: apply-app（アプリ層）→ seed（データ投入）の順で実行します。")


def cmd_apply_app(assume_yes: bool = False, knowledge_mcp_desired_count: int = 1) -> None:
    cfg = config.load_config()
    prerequisites(cfg)
    tfvars.validate("app")
    d = paths.app_dir()
    image_tag = _image_tag()
    log.info(f"region={cfg.aws_region} / image_tag={image_tag} / state_bucket={cfg.state_bucket} / key={cfg.state_key_app}")

    log.step("database 構成の apply 済み確認")
    _require_database_applied(cfg)  # app は terraform_remote_state で database 出力を参照
    log.ok("database 構成 state を確認")

    prompts.confirm_or_exit(
        f"AWS 上に ECS クラスタ/サービス等の課金リソースを作成します（リージョン: {cfg.aws_region}）。",
        assume_yes,
    )
    ensure_state_bucket(cfg)  # 単独実行時の保険

    log.step("app 構成 init（S3 バックエンド）")
    tf.init_backend(d, cfg.state_bucket, cfg.aws_region, cfg.state_key_app)

    log.step("ECR リポジトリ作成（knowledge-mcp / tag-selector-mcp / agent-invitro / mcp-inspector）")
    tf.apply(d, targets=["module.ecr"], what="ECR apply")
    repos = tf.output_json(d, "ecr_repository_urls")
    registry = repos["knowledge-mcp"].split("/")[0]

    log.step("Docker イメージ build / push")
    log.info(f"ECR ログイン: {registry}")
    dockercli.login(registry, cfg.aws_region)
    # mcp-inspector（4本目）は検証専用で Phase 6 に手動 build/push（§5.7）。
    components = [
        ("knowledge_mcp", "knowledge-mcp"),
        ("tag_selector_mcp", "tag-selector-mcp"),
        ("agent_invitro", "agent-invitro"),
    ]
    for src_dir, repo in components:
        image = f"{repos[repo]}:{image_tag}"
        dockercli.build_and_push(paths.repo_root() / src_dir, image, src_dir, repo)
    log.ok("3イメージの push 完了（mcp-inspector は検証時に手動 build/push, §5.7）")

    log.step(f"app 構成 apply（knowledge_mcp_desired_count={knowledge_mcp_desired_count}）")
    tf.apply(d, variables={"knowledge_mcp_desired_count": knowledge_mcp_desired_count}, what="app apply")

    log.step("app 構成 apply 完了")
    cluster = None
    try:
        cluster = tf.output_raw(d, "cluster_name")
        log.info(f"cluster: {cluster}")
    except DeployError:
        log.warn("output 'cluster_name' を取得できませんでした（apply 自体は完了しています）。")

    if knowledge_mcp_desired_count == 0:
        log.warn("knowledge_mcp は停止中（desired_count=0）。seed 完了後に再 apply（=1）で起動します。")
    elif cluster:
        # サーバ(knowledge/tag)が起動する構成のときだけ、クライアントを登録後に起動させ直す。
        _reconcile_agent_after_servers(cluster, cfg.aws_region)

    log.info("検証（Phase 6）: mcp-inspector イメージを手動 build/push 後に run-task + ECS Exec（README 参照）。")


def cmd_seed(assume_yes: bool = False) -> None:
    cfg = config.load_config()
    prerequisites(cfg)
    region = cfg.aws_region

    log.step("database / app 構成の apply 済み確認")
    _require_database_applied(cfg)
    _require_app_applied(cfg)
    log.ok("両構成の state を確認")

    db, app = paths.database_dir(), paths.app_dir()

    log.step("database 構成 output 取得")
    tf.init_backend(db, cfg.state_bucket, region, cfg.state_key_database)
    subnets = tf.output_json(db, "private_subnet_ids")
    sg = tf.output_raw(db, "sg_verification_task_id")
    family = tf.output_raw(db, "db_init_task_family")
    if not subnets or not sg or not family:
        raise DeployError("database 構成の output（private_subnet_ids / sg_verification_task_id / db_init_task_family）を取得できませんでした。")

    log.step("app 構成 output 取得")
    tf.init_backend(app, cfg.state_bucket, region, cfg.state_key_app)
    cluster = tf.output_raw(app, "cluster_name")
    if not cluster:
        raise DeployError("app 構成の output（cluster_name）を取得できませんでした。")

    log_group = f"/ecs/{family}"
    log.step(f"シード run-task 起動（{family}）")
    task_arn = aws.run_seed_task(cluster, family, subnets, sg, region)
    log.info(f"task: {task_arn}")

    task = aws.wait_task_stopped(cluster, task_arn, region)
    exit_code = aws.task_exit_code(task)
    if str(exit_code) != "0":
        raise DeployError(f"シードが異常終了しました (exitCode={exit_code})。CloudWatch Logs {log_group} を確認してください。")
    log.ok("シード完了（exitCode=0）")
    log.info("knowledge_mcp を起動するには apply-app（desired_count=1）を実行してください（apply-all は自動で行います）。")


def cmd_apply_all(assume_yes: bool = False) -> None:
    cfg = config.load_config()
    prerequisites(cfg)
    log.step("apply-all: database -> app(gate closed) -> seed -> app(gate open)")
    log.info(f"state_bucket={cfg.state_bucket} / database key={cfg.state_key_database} / app key={cfg.state_key_app}")
    prompts.confirm_or_exit(
        f"AWS 上に database 構成（RDS 等）と app 構成（ECS 等）の課金リソースを作成し、シードまで一括実行します（リージョン: {cfg.aws_region}）。",
        assume_yes,
    )

    log.step("[1/4] database 構成 apply")
    cmd_apply_database(assume_yes=True)

    log.step("[2/4] app 構成 apply（ゲート閉: knowledge_mcp_desired_count=0）")
    cmd_apply_app(assume_yes=True, knowledge_mcp_desired_count=0)

    log.step("[3/4] シード（run-task, exitCode=0 まで待機）")
    cmd_seed(assume_yes=True)

    log.step("[4/4] app 構成 再 apply（ゲート開: knowledge_mcp_desired_count=1）")
    cmd_apply_app(assume_yes=True, knowledge_mcp_desired_count=1)

    log.step("apply-all 完了")
    log.info("次の手動検証（Phase 6, README 参照）: MCP Inspector を ECR に build/push 後 run-task + ECS Exec、agent_invitro に ipython で手動テストクエリ3件。")
    log.info("破棄はコスト管理目的なら destroy-app（RDS は残る）。DB も破棄するなら destroy-database。")


def cmd_destroy_app() -> None:
    cfg = config.load_config()
    prerequisites(cfg)
    log.step("app 構成の破棄（RDS・ネットワークは残す, ADR-0039）")
    log.warn("app 構成（ECS クラスタ/3サービス/MCP Inspector タスク定義/予算アラート/ECR4）を削除します。RDS・SG・VPCエンドポイントは残ります。")
    prompts.confirm_typed("app 構成を破棄する場合は 'destroy-app' と入力してください: ", "destroy-app")

    d = paths.app_dir()
    tf.init_backend(d, cfg.state_bucket, cfg.aws_region, cfg.state_key_app)
    tf.destroy(d, variables={"knowledge_mcp_desired_count": 0}, what="app destroy")

    log.ok("app 構成の破棄完了")
    log.info("RDS は database 構成に残っています。再開時は apply-app のみでよい（再シード不要）。")
    log.info("DB も破棄するなら destroy-database を実行してください（app 破棄後に実行すること）。")


def cmd_destroy_database() -> None:
    cfg = config.load_config()
    prerequisites(cfg)
    log.step("database 構成の破棄（RDS を含む, 取り消し不可）")
    log.warn("RDS インスタンスと投入済み QA/タグデータを完全に削除します。再構築には再シード（Bedrock 再計算）が必要です。")

    # destroy 順序（app -> database）ガード: app state が残っていれば警告。
    if aws.object_exists(cfg.state_bucket, cfg.state_key_app):
        log.warn(f"app 構成の state が残っています（s3://{cfg.state_bucket}/{cfg.state_key_app}）。")
        log.warn("app 構成が生存していると、ECS が database 構成の SG/サブネットを使用中で destroy が失敗する可能性があります。")
        log.warn("先に destroy-app を実行してから本操作を行うことを強く推奨します（ADR-0039 destroy 順序）。")

    prompts.confirm_typed("DB を破棄する場合は 'destroy-database' と入力してください: ", "destroy-database")

    d = paths.database_dir()
    tf.init_backend(d, cfg.state_bucket, cfg.aws_region, cfg.state_key_database)

    # 1) 削除保護を解除（deletion_protection=true のままでは destroy できない）。
    log.step("削除保護の解除（apply）")
    tf.apply(d, variables={"deletion_protection": "false"}, what="deletion_protection 解除 apply")

    # 2) 破棄。
    log.step("database 構成 破棄（destroy）")
    tf.destroy(d, variables={"deletion_protection": "false", "skip_final_snapshot": "true"}, what="database destroy")

    log.ok("database 構成の破棄完了")
    log.info("VPC エンドポイント等も削除されました（既存 VPC/サブネット自体は data 参照のため残存）。")


def cmd_shell() -> None:
    """TF_VAR_* を設定済みの状態でコンテナ内 bash に入る（旧 load-env.ps1 の代替）。"""
    cfg = config.load_config()
    log.info(f"TF_VAR_* をエクスポート済み（state_bucket={cfg.state_bucket}, region={cfg.aws_region}）。")
    log.info("この bash 内では各構成ディレクトリで直接 terraform を実行できます（例: cd main/database && terraform plan）。")
    os.execvp("bash", ["bash"])
