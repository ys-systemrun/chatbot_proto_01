"""マイグレーション専用モード（ADR-0075）の cmd_migrate / cmd_seed(skip_seed) を検証する。

実 AWS には触れず、aws / tf / config をスタブし、
- migrate は MIGRATE_ONLY=true の environment オーバーライドで run-task を起動すること
- seed --skip-seed が migrate と同一（MIGRATE_ONLY=true, run_import_task 経路）になること
- seed（オプションなし）は既存どおり run_seed_task（オーバーライドなし）を使うこと
- 非破壊的経路のみを通り、確認プロンプト（confirm_typed）を呼ばないこと
- 異常終了（exitCode!=0）で DeployError になること
を確認する。
"""

import pytest

from src import commands
from src.config import Config


def _dummy_cfg():
    return Config("bucket", "us-east-1", "acct", "prefix", "database/state.tfstate", "app/state.tfstate", {})


def _output_raw(_cwd, name):
    return {
        "sg_verification_task_id": "sg-1",
        "db_init_task_family": "db-hiroba-qa-init",
        "cluster_name": "prefix-cluster",
    }[name]


def _wire_common(monkeypatch, calls, *, exit_code="0"):
    monkeypatch.setattr(commands.config, "load_config", lambda *a, **k: _dummy_cfg())
    monkeypatch.setattr(commands, "prerequisites", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_require_database_applied", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_require_app_applied", lambda *a, **k: None)

    monkeypatch.setattr(commands.tf, "init_backend", lambda *a, **k: None)
    monkeypatch.setattr(commands.tf, "output_json", lambda *a, **k: ["subnet-1"])
    monkeypatch.setattr(commands.tf, "output_raw", _output_raw)

    # confirm_typed を呼んだら即失敗させ、確認プロンプトが無いことを保証する。
    def _no_confirm(*a, **k):
        raise AssertionError("マイグレーション専用モードで confirm_typed が呼ばれた（ADR-0075 は確認なし）")

    monkeypatch.setattr(commands.prompts, "confirm_typed", _no_confirm)

    def _run_import_task(cluster, family, subnets, sg, region, container_name, environment):
        calls.append(("import", environment.get("MIGRATE_ONLY"), environment.get("IMPORT_MODE")))
        return "task-arn-import"

    def _run_seed_task(cluster, family, subnets, sg, region):
        calls.append(("seed", None, None))
        return "task-arn-seed"

    monkeypatch.setattr(commands.aws, "run_import_task", _run_import_task)
    monkeypatch.setattr(commands.aws, "run_seed_task", _run_seed_task)
    monkeypatch.setattr(commands.aws, "wait_task_stopped", lambda *a, **k: {"containers": []})
    monkeypatch.setattr(commands.aws, "task_exit_code", lambda t: exit_code)


def test_migrate_sets_migrate_only_override(monkeypatch):
    calls = []
    _wire_common(monkeypatch, calls)

    commands.cmd_migrate()

    # MIGRATE_ONLY=true の environment オーバーライドで run_import_task を1回だけ呼ぶ。
    assert calls == [("import", "true", None)]


def test_seed_skip_seed_matches_migrate(monkeypatch):
    calls = []
    _wire_common(monkeypatch, calls)

    commands.cmd_seed(skip_seed=True)

    # migrate と同一（MIGRATE_ONLY=true, run_import_task 経路。run_seed_task は使わない）。
    assert calls == [("import", "true", None)]


def test_seed_default_uses_seed_task(monkeypatch):
    calls = []
    _wire_common(monkeypatch, calls)

    commands.cmd_seed()

    # 既存動作: environment オーバーライドなしの run_seed_task を使う（後方互換）。
    assert calls == [("seed", None, None)]


def test_migrate_raises_on_nonzero_exit(monkeypatch):
    calls = []
    _wire_common(monkeypatch, calls, exit_code="1")

    with pytest.raises(commands.DeployError):
        commands.cmd_migrate()
