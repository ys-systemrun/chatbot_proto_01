"""terraform 呼び出し（subprocess のリスト引数）。

`-target=...` や `-var=key=value` は 1 引数として渡すため、PowerShell 5.1 の引数分割は起きない。
変数は原則 .env の TF_VAR_* から供給し、実行時に上書きしたいものだけ -var で渡す
（-var は TF_VAR_ より優先される）。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import proc

TERRAFORM = "terraform"


def init_backend(cwd: Path, bucket: str, region: str, key: str) -> None:
    proc.run(
        [
            TERRAFORM, "init", "-input=false", "-reconfigure",
            f"-backend-config=bucket={bucket}",
            f"-backend-config=region={region}",
            f"-backend-config=key={key}",
            "-backend-config=use_lockfile=true",
        ],
        cwd=cwd,
        what=f"{key} init",
    )


def init_local(cwd: Path) -> None:
    proc.run([TERRAFORM, "init", "-input=false"], cwd=cwd, what="bootstrap init")


def apply(cwd: Path, targets: list[str] | None = None, variables: dict | None = None, what: str = "terraform apply") -> None:
    cmd = [TERRAFORM, "apply", "-auto-approve", "-input=false"]
    for target in targets or []:
        cmd.append(f"-target={target}")
    for key, value in (variables or {}).items():
        cmd.append(f"-var={key}={value}")
    proc.run(cmd, cwd=cwd, what=what)


def destroy(cwd: Path, variables: dict | None = None, what: str = "terraform destroy") -> None:
    cmd = [TERRAFORM, "destroy", "-auto-approve", "-input=false"]
    for key, value in (variables or {}).items():
        cmd.append(f"-var={key}={value}")
    proc.run(cmd, cwd=cwd, what=what)


def output_raw(cwd: Path, name: str) -> str:
    return proc.capture([TERRAFORM, "output", "-raw", name], cwd=cwd, what=f"terraform output {name}").strip()


def output_json(cwd: Path, name: str):
    return json.loads(proc.capture([TERRAFORM, "output", "-json", name], cwd=cwd, what=f"terraform output {name}"))
