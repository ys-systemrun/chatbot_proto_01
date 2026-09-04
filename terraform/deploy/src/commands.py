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

    log.step("ECR リポジトリ作成（knowledge-mcp / tag-selector-mcp / agent-invitro / mcp-inspector / admin-ui）")
    tf.apply(d, targets=["module.ecr"], what="ECR apply")
    repos = tf.output_json(d, "ecr_repository_urls")
    registry = repos["knowledge-mcp"].split("/")[0]

    log.step("Docker イメージ build / push")
    log.info(f"ECR ログイン: {registry}")
    dockercli.login(registry, cfg.aws_region)
    # mcp-inspector（検証専用）は Phase 6 に手動 build/push（§5.7）。
    components = [
        ("knowledge_mcp", "knowledge-mcp"),
        ("tag_selector_mcp", "tag-selector-mcp"),
        ("agent_invitro", "agent-invitro"),
    ]
    for src_dir, repo in components:
        image = f"{repos[repo]}:{image_tag}"
        dockercli.build_and_push(paths.repo_root() / src_dir, image, src_dir, repo)

    # admin_ui（管理UI, IMPL-202608211050 T16）: 例外的にビルドコンテキスト＝リポジトリルート、
    # Dockerfile＝web_backend/Dockerfile.admin_ui（front_dev のビルド＋web_backend のマルチステージ）。
    admin_ui_image = f"{repos['admin-ui']}:{image_tag}"
    dockercli.build_and_push(
        paths.repo_root(),
        admin_ui_image,
        "admin_ui",
        "admin-ui",
        dockerfile="web_backend/Dockerfile.admin_ui",
    )
    log.ok("4イメージの push 完了（mcp-inspector は検証時に手動 build/push, §5.7）")

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


def _run_db_init_task(cfg: config.Config, *, migrate_only: bool, label: str) -> None:
    """db_init_task_family を run-task 起動し exitCode=0 まで待つ共通処理（seed / migrate 共用）。

    migrate_only=True のとき、run-task に MIGRATE_ONLY=true の environment オーバーライドを付与して
    起動し、db_hiroba_qa_init のシード投入（手順3）のみをスキップさせる（ADR-0075）。それ以外の
    処理（両構成 apply 済み確認・output 取得・run-task・STOPPED 待機・exitCode 確認）は seed と同一。
    IMPORT_MODE と同型の environment オーバーライド機構（run_import_task, ADR-0066）を再利用する。
    """
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
    if migrate_only:
        log.step(f"{label} run-task 起動（{family}, MIGRATE_ONLY）")
        task_arn = aws.run_import_task(
            cluster, family, subnets, sg, region,
            container_name=family, environment={"MIGRATE_ONLY": "true"},
        )
    else:
        log.step(f"{label} run-task 起動（{family}）")
        task_arn = aws.run_seed_task(cluster, family, subnets, sg, region)
    log.info(f"task: {task_arn}")

    task = aws.wait_task_stopped(cluster, task_arn, region)
    exit_code = aws.task_exit_code(task)
    if str(exit_code) != "0":
        raise DeployError(f"{label}が異常終了しました (exitCode={exit_code})。CloudWatch Logs {log_group} を確認してください。")
    log.ok(f"{label}完了（exitCode=0）")


def cmd_seed(assume_yes: bool = False, skip_seed: bool = False) -> None:
    """シード run-task を起動する（再シード用途）。

    skip_seed=True のときはマイグレーション専用モード（MIGRATE_ONLY=true）で起動し、シード投入を
    除外して migrate コマンドと同一結果になる（ADR-0075）。未指定時は既存動作（6ステップ全実行）
    を完全に維持する（後方互換）。いずれも非破壊的操作のため確認プロンプトは設けない。
    """
    cfg = config.load_config()
    prerequisites(cfg)
    if skip_seed:
        _run_db_init_task(cfg, migrate_only=True, label="マイグレーション")
        return
    _run_db_init_task(cfg, migrate_only=False, label="シード")
    log.info("knowledge_mcp を起動するには apply-app（desired_count=1）を実行してください（apply-all は自動で行います）。")


def cmd_migrate() -> None:
    """マイグレーション専用モードで db_hiroba_qa_init の run-task を起動する（ADR-0075）。

    cmd_seed(skip_seed=True) と同一結果（MIGRATE_ONLY=true）。シード投入（embedding 計算を伴いうる
    手順3）を除外し、両データベースのロール作成・マイグレーション適用・権限付与・エクスポート専用
    ロール作成のみを実行する。スキーマ変更のみを RDS に反映したいとき（データ投入・更新は引き続き
    import-data を使う）に用いる。非破壊的操作のため確認プロンプトは設けない（無人実行可）。
    """
    cfg = config.load_config()
    prerequisites(cfg)
    _run_db_init_task(cfg, migrate_only=True, label="マイグレーション")


# 全データインポート（ADR-0066）: 実行対象データベースと、停止すべき（そのデータベースへ直接
# 接続する）アプリケーションサービスの対応。admin_ui は AWS 上の web_backend（管理UI）。
# agent_invitro はデータベースへ直接接続しないため停止対象に含めない（ADR-0066 §8 の検討）。
_IMPORT_SERVICES_BY_DB = {
    "chatbot": ["admin_ui", "knowledge_mcp", "tag_selector_mcp"],
    "conversation": ["admin_ui"],
}
_IMPORT_DUMP_DEFAULT = {"chatbot": "chatbot.sql", "conversation": "conversation.sql"}


def _import_labels(target: str) -> list[str]:
    if target == "both":
        return ["chatbot", "conversation"]
    if target in ("chatbot", "conversation"):
        return [target]
    raise DeployError(f"--target は chatbot / conversation / both のいずれか（指定: {target!r}）。")


def _import_services(labels: list[str]) -> list[str]:
    """対象ラベル群に対応する停止対象サービスの重複なしリスト（定義順を保持）。"""
    ordered: list[str] = []
    for svc in ("admin_ui", "knowledge_mcp", "tag_selector_mcp"):
        if any(svc in _IMPORT_SERVICES_BY_DB[label] for label in labels) and svc not in ordered:
            ordered.append(svc)
    return ordered


def cmd_import_data(
    target: str = "both",
    chatbot_sql: str | None = None,
    conversation_sql: str | None = None,
    assume_yes: bool = False,
) -> None:
    """全データインポート（全消去→上書き）バッチ（ADR-0066）。

    ローカルの SQL ダンプを S3 へアップロード → 対象サービス停止 → db_hiroba_qa_init を
    IMPORT_MODE で run-task（事前バックアップ→全消去→上書き投入）→ 完了後サービス再開。
    破壊的操作のため、実行前に対象クラスタ名のタイプ確認を必須とする（§6）。
    """
    cfg = config.load_config()
    prerequisites(cfg)
    region = cfg.aws_region
    labels = _import_labels(target)

    log.step("database / app 構成の apply 済み確認")
    _require_database_applied(cfg)
    _require_app_applied(cfg)
    log.ok("両構成の state を確認")

    # 投入ダンプ（ローカルファイル）の解決・存在確認。
    dump_paths: dict[str, str] = {}
    overrides = {"chatbot": chatbot_sql, "conversation": conversation_sql}
    for label in labels:
        path = overrides[label] or _IMPORT_DUMP_DEFAULT[label]
        if not os.path.isfile(path):
            raise DeployError(
                f"{label} の投入ダンプが見つかりません: {path}\n"
                f"  エクスポート機能が生成した {_IMPORT_DUMP_DEFAULT[label]} を terraform/ に置くか、"
                f"  --{label.replace('_', '-')}-sql でパスを指定してください。"
            )
        dump_paths[label] = path

    db, app = paths.database_dir(), paths.app_dir()

    log.step("database 構成 output 取得")
    tf.init_backend(db, cfg.state_bucket, region, cfg.state_key_database)
    subnets = tf.output_json(db, "private_subnet_ids")
    sg = tf.output_raw(db, "sg_verification_task_id")
    family = tf.output_raw(db, "db_init_task_family")
    import_bucket = tf.output_raw(db, "import_bucket_name")
    if not subnets or not sg or not family or not import_bucket:
        raise DeployError(
            "database 構成の output（private_subnet_ids / sg_verification_task_id / "
            "db_init_task_family / import_bucket_name）を取得できませんでした。"
        )

    log.step("app 構成 output 取得")
    tf.init_backend(app, cfg.state_bucket, region, cfg.state_key_app)
    cluster = tf.output_raw(app, "cluster_name")
    if not cluster:
        raise DeployError("app 構成の output（cluster_name）を取得できませんでした。")

    services = _import_services(labels)

    log.warn("=== 全データインポート（全消去→上書き, 不可逆） ===")
    log.warn(f"対象データベース: {', '.join(labels)}")
    log.warn(f"投入ダンプ: {', '.join(f'{k}={v}' for k, v in dump_paths.items())}")
    log.warn(f"停止するサービス: {', '.join(services)}")
    log.warn(
        f"実行内容: 事前バックアップを s3://{import_bucket}/rollback/ に保存 → 対象テーブルを"
        " 全消去 → 上記ダンプで上書き投入。既存データは全消去されます。"
    )
    prompts.confirm_typed(
        f"実行する場合は対象クラスタ名 '{cluster}' を入力してください: ", cluster
    )

    # 1. 投入ダンプを S3 へアップロード（§7）。
    log.step("投入ダンプを S3 へアップロード")
    for label, path in dump_paths.items():
        key = f"import/{label}.sql"
        aws.upload_file(import_bucket, key, path, region)
        log.ok(f"s3://{import_bucket}/{key} ← {path}")

    # 2. メンテナンス: 対象サービスを停止（desired_count=0）。停止前の値を控える（§8）。
    prior_counts: dict[str, int] = {}
    try:
        log.step("対象サービスの停止（desired_count=0）")
        for svc in services:
            prior_counts[svc] = aws.service_desired_count(cluster, svc, region)
            aws.set_service_desired_count(cluster, svc, 0, region)
            log.info(f"{svc}: desired_count {prior_counts[svc]} -> 0")
        if services:
            aws.wait_services_stable(cluster, services, region)
            log.ok("対象サービス停止完了")

        # 3. IMPORT_MODE の run-task を起動し、exitCode=0 まで待機（§1）。
        log_group = f"/ecs/{family}"
        env = {
            "IMPORT_MODE": "true",
            "IMPORT_TARGET": target,
            "IMPORT_BUCKET": import_bucket,
            "AWS_REGION": region,
        }
        log.step(f"インポート run-task 起動（{family}, IMPORT_MODE, target={target}）")
        task_arn = aws.run_import_task(
            cluster, family, subnets, sg, region, container_name=family, environment=env
        )
        log.info(f"task: {task_arn}")
        task = aws.wait_task_stopped(cluster, task_arn, region)
        exit_code = aws.task_exit_code(task)
        if str(exit_code) != "0":
            raise DeployError(
                f"インポートが異常終了しました (exitCode={exit_code})。CloudWatch Logs "
                f"{log_group} を確認してください。退避バックアップは "
                f"s3://{import_bucket}/rollback/ に保存済みです（§5）。"
            )
        log.ok("インポート完了（exitCode=0）")
    finally:
        # 4. 停止したサービスを停止前の値へ戻して安定化（成功・失敗どちらでも再開する, §8）。
        if prior_counts:
            log.step("対象サービスの再開（停止前の desired_count へ復元）")
            for svc, count in prior_counts.items():
                try:
                    aws.set_service_desired_count(cluster, svc, count, region)
                    log.info(f"{svc}: desired_count -> {count}")
                except Exception as exc:  # noqa: BLE001 - 再開失敗は警告に留め、他サービスの復元は続ける
                    log.warn(f"{svc} の再開に失敗しました: {exc}")
            try:
                aws.wait_services_stable(cluster, list(prior_counts.keys()), region)
                log.ok("対象サービス再開完了")
            except Exception as exc:  # noqa: BLE001
                log.warn(f"サービス安定待機に失敗しました: {exc}")

    log.step("全データインポート完了")
    log.info(f"退避バックアップ: s3://{import_bucket}/rollback/<対象>/<時刻>/（復旧手段, §5）")


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
