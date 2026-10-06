"""評価ランナーの CLI（ADR-0099 §5）。evals\\eval.bat から `python -m runner <コマンド>` で呼ばれる。

段階①では `pull-feedback` のみ。`run` / `compare` / `snapshot` は段階③④で追加する。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import feedback

EVALS_DIR = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> dict[str, str]:
    """evals/.env（KEY=VALUE, '#' コメント）を読む。無ければ空。"""
    values: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _base_url(arg: str | None) -> str:
    url = arg or os.environ.get("EVAL_BASE_URL") or _load_env(EVALS_DIR / ".env").get("EVAL_BASE_URL")
    if not url:
        sys.exit(
            "EVAL_BASE_URL が未設定です。evals/.env.example を evals/.env にコピーし、admin_ui の URL"
            "（apply-app の出力 admin_ui_alb_dns_name に http:// を付けたもの）を記入してください。"
        )
    return url


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="eval", description="chatbot_invitro 評価ランナー（ADR-0099）")
    sub = parser.add_subparsers(dest="command", required=True)
    pf = sub.add_parser("pull-feedback", help="人手評価（👍/👎・理由・リリース）の増分を evals/feedback/ に取り込む")
    pf.add_argument("--base-url", default=None, help="admin_ui の URL（既定: evals/.env の EVAL_BASE_URL）")
    args = parser.parse_args(argv)

    if args.command == "pull-feedback":
        base_url = _base_url(args.base_url)
        print(f"取得元: {base_url}/api/evaluated_messages")
        path = feedback.pull(base_url, EVALS_DIR / "feedback")
        if path is None:
            print("新しい評価はありません。")
            return
        print(feedback.summarize(path))
        print(f"保存先: evals/feedback/{path.name}")


if __name__ == "__main__":
    main()
