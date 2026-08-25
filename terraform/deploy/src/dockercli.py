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


def build_and_push(
    context: Path,
    image: str,
    dir_label: str,
    repo_label: str,
    dockerfile: str | None = None,
) -> None:
    log.info(f"build: {dir_label} -> {image}")
    build_cmd = ["docker", "build", "-t", image]
    # admin_ui はビルドコンテキストをリポジトリルートにし、Dockerfile を明示指定する
    # （front_dev/ と web_backend/ の両方を COPY するため, IMPL-202608211050 T6/5.5）。
    # dockerfile はコンテキスト（context）からの相対パスで渡す。
    if dockerfile is not None:
        build_cmd += ["-f", str(context / dockerfile)]
    build_cmd.append(str(context))
    proc.run(build_cmd, what=f"docker build ({dir_label})")
    proc.run(["docker", "push", image], what=f"docker push ({repo_label})")
