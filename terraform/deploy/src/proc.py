"""外部コマンド実行ヘルパ。

すべて subprocess のリスト引数（shell=False）で呼ぶ。これにより PowerShell 5.1 で起きた
「-target=module.ecr の分割」や「native→native パイプのトークン破損」は原理的に発生しない。
text=True, encoding="utf-8" 固定で CP932 誤デコードも起きない。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import DeployError


def _cwd(cwd: Path | str | None) -> str | None:
    return str(cwd) if cwd is not None else None


def run(cmd: list[str], cwd=None, what: str | None = None, input_text: str | None = None):
    """コマンドを実行し、出力はそのまま端末へ流す。終了コード != 0 なら DeployError。"""
    result = subprocess.run(
        [str(c) for c in cmd],
        cwd=_cwd(cwd),
        input=input_text,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise DeployError(f"{what or ' '.join(map(str, cmd))} に失敗しました (exit {result.returncode})")
    return result


def capture(cmd: list[str], cwd=None, what: str | None = None) -> str:
    """stdout を取得して返す。終了コード != 0 なら DeployError。"""
    result = subprocess.run(
        [str(c) for c in cmd],
        cwd=_cwd(cwd),
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise DeployError(f"{what or ' '.join(map(str, cmd))} に失敗しました (exit {result.returncode}): {detail}")
    return result.stdout


def capture_result(cmd: list[str], cwd=None):
    """終了コードで判定したいだけの場合（例外を投げない）。CompletedProcess を返す。"""
    return subprocess.run(
        [str(c) for c in cmd],
        cwd=_cwd(cwd),
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
