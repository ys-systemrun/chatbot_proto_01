"""色付きコンソール出力（旧 common.ps1 の Write-Step/Info/Ok/Warn/Fail 相当）。"""

from __future__ import annotations

import sys


def _c(code: str, msg: str) -> str:
    return f"\033[{code}m{msg}\033[0m"


def step(msg: str) -> None:
    print("\n" + _c("1;36", f"==== {msg} ===="))


def info(msg: str) -> None:
    print(_c("90", f"  {msg}"))


def ok(msg: str) -> None:
    print(_c("32", f"  OK: {msg}"))


def warn(msg: str) -> None:
    print(_c("33", f"  WARN: {msg}"))


def error(msg: str) -> None:
    print(_c("31", f"\nERROR: {msg}"), file=sys.stderr)
