"""AWS 操作（boto3）。

旧スクリプトの `aws sts/s3api/ecr/ecs ...` を boto3 に置き換え。
- ECR ログインは get_authorization_token を base64 デコードして user/password を得る
  （`aws ecr get-login-password | docker login` のパイプを廃し、トークン破損を回避）。

boto3 はイメージにのみ同梱される想定のため、import は関数内で遅延する
（config / tfvars / commands をホスト（boto3 無し）でも import・テストできるようにする）。
"""

from __future__ import annotations

import base64
import time

from . import log
from .errors import DeployError


def _client(service: str, **kwargs):
    import boto3

    return boto3.client(service, **kwargs)


def account_id() -> str:
    return _client("sts").get_caller_identity()["Account"]


def check_account(expected: str) -> str:
    ident = account_id()
    if expected and ident != expected:
        raise DeployError(
            f"認証先アカウント({ident})が .env の AWS_ACCOUNT_ID({expected})と一致しません。"
        )
    return ident


def bucket_exists(bucket: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        _client("s3").head_bucket(Bucket=bucket)
        return True
    except ClientError:
        return False


def object_exists(bucket: str, key: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        _client("s3").head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def ecr_login(region: str) -> "tuple[str, str]":
    """(username, password) を返す。password は認証トークンを base64 デコードした後半部分。"""
    resp = _client("ecr", region_name=region).get_authorization_token()
    token = resp["authorizationData"][0]["authorizationToken"]
    user, password = base64.b64decode(token).decode("utf-8").split(":", 1)
    return user, password


def run_seed_task(cluster: str, family: str, subnets, security_group: str, region: str) -> str:
    ecs = _client("ecs", region_name=region)
    resp = ecs.run_task(
        cluster=cluster,
        launchType="FARGATE",
        taskDefinition=family,
        enableExecuteCommand=True,
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": subnets,
                "securityGroups": [security_group],
                "assignPublicIp": "DISABLED",
            }
        },
    )
    tasks = resp.get("tasks", [])
    if not tasks:
        raise DeployError(f"シードの run-task 起動に失敗しました: {resp.get('failures', [])}")
    return tasks[0]["taskArn"]


def wait_task_stopped(cluster: str, task_arn: str, region: str, timeout_sec: int = 1800, interval_sec: int = 15) -> dict:
    ecs = _client("ecs", region_name=region)
    elapsed = 0
    while True:
        time.sleep(interval_sec)
        elapsed += interval_sec
        tasks = ecs.describe_tasks(cluster=cluster, tasks=[task_arn]).get("tasks", [])
        status = tasks[0]["lastStatus"] if tasks else "UNKNOWN"
        log.info(f"status={status} ({elapsed}s)")
        if status == "STOPPED":
            return tasks[0]
        if elapsed >= timeout_sec:
            raise DeployError(f"シードがタイムアウトしました（{timeout_sec}s）。")


def task_exit_code(task: dict):
    containers = task.get("containers", [])
    return containers[0].get("exitCode") if containers else None


def wait_services_stable(cluster: str, services: list[str], region: str) -> None:
    """ECS サービスが steady state（desired 数のタスクが RUNNING で安定）になるまで待つ。"""
    ecs = _client("ecs", region_name=region)
    ecs.get_waiter("services_stable").wait(cluster=cluster, services=services)


def force_new_deployment(cluster: str, service: str, region: str) -> None:
    """サービスを強制再デプロイ（同一 :latest イメージや Service Connect 再構成を反映させる）。"""
    _client("ecs", region_name=region).update_service(
        cluster=cluster, service=service, forceNewDeployment=True
    )
