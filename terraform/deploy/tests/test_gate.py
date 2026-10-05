"""apply-all のゲート順序（database -> app(0) -> seed -> app(1)）を検証する。

commands をそのまま import できるよう、aws.py は boto3 を遅延 import している。
実 AWS には触れず、サブコマンド・前提・プロンプトを stub して呼び出し順だけを確認する。
"""

from src import commands
from src.config import Config


def test_apply_all_gate_sequence(monkeypatch):
    calls = []
    dummy = Config("bucket", "us-east-1", "acct", "prefix", "database/state.tfstate", "app/state.tfstate", {})

    monkeypatch.setattr(commands.config, "load_config", lambda *a, **k: dummy)
    monkeypatch.setattr(commands, "prerequisites", lambda *a, **k: None)
    monkeypatch.setattr(commands.prompts, "confirm_or_exit", lambda *a, **k: None)
    monkeypatch.setattr(commands, "cmd_apply_datastore", lambda **k: calls.append(("datastore", k)))
    monkeypatch.setattr(commands, "cmd_apply_database", lambda **k: calls.append(("database", k)))
    monkeypatch.setattr(commands, "cmd_apply_app", lambda **k: calls.append(("app", k)))
    monkeypatch.setattr(commands, "cmd_seed", lambda **k: calls.append(("seed", k)))

    commands.cmd_apply_all(assume_yes=True)

    # ADR-0097: DVC リモート（datastore）を先に冪等 apply してから database を build する。
    assert [name for name, _ in calls] == ["datastore", "database", "app", "seed", "app"]
    # ゲート閉→開（ADR-0095: 集約サービス全体の desired_count）
    assert calls[2][1]["app_desired_count"] == 0
    assert calls[4][1]["app_desired_count"] == 1


def test_apply_app_desired_count_flag_and_legacy_alias():
    from src.__main__ import build_parser

    parser = build_parser()
    assert parser.parse_args(["apply-app", "--app-desired-count", "0"]).app_desired_count == 0
    # 旧名（ADR-0095 以前）も互換のため受け付ける。
    assert parser.parse_args(["apply-app", "--knowledge-mcp-desired-count", "0"]).app_desired_count == 0
    assert parser.parse_args(["apply-app"]).app_desired_count == 1
