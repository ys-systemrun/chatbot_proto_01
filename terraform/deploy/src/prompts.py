"""対話確認（旧 Confirm-Or-Exit / Read-Host によるタイプ確認）。

TTY 前提（.bat は docker run -it で起動）。破棄系のタイプ確認は assume_yes で省略できない
（誤破棄防止のため常に人間の入力を要求する）。
"""

from __future__ import annotations


def confirm_or_exit(message: str, assume_yes: bool) -> None:
    if assume_yes:
        print(f"  (自動承認: {message})")
        return
    ans = input(f"{message}  続行しますか? [y/N] ").strip()
    if ans not in ("y", "Y"):
        print("中止しました。")
        raise SystemExit(0)


def confirm_typed(prompt: str, expected: str) -> None:
    ans = input(prompt).strip()
    if ans != expected:
        print("中止しました。")
        raise SystemExit(0)
