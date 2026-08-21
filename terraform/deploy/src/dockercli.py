"""docker CLI 呼び出し（ホスト Docker デーモンをソケット共有で駆動 = DooD）。

login/build/push はすべてコンテナ内 docker CLI から実行され、同一の ~/.docker/config.json を
使うため push 時も認証が引き継がれる。login はパイプを使わず --password-stdin に input で渡す。
"""

from __future__ import annotations

from pathlib import Path

from . import aws, log, proc


def login(registry: str, region: str) -> None:
    user, password = aws.ecr_login(region)
    proc.run(
        ["docker", "login", "--username", user, "--password-stdin", registry],
        what="ECR への docker login",
        input_text=password,
    )


def build_and_push(context: Path, image: str, dir_label: str, repo_label: str) -> None:
    log.info(f"build: {dir_label} -> {image}")
    proc.run(["docker", "build", "-t", image, str(context)], what=f"docker build ({dir_label})")
    proc.run(["docker", "push", image], what=f"docker push ({repo_label})")
