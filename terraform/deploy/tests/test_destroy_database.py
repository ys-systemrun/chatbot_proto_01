"""cmd_destroy_database の削除保護解除ステップを検証する。

実 AWS / terraform には触れず、tf / config / prompts をスタブし、
- RDS が state にあるときは、削除保護の解除 apply を RDS インスタンスだけに -target で絞ること
- RDS が state に無いときは、解除 apply をスキップして destroy だけを行うこと
  （対象を絞らない apply が RDS を新規作成しようとする事象の再発防止）
- state が空なら apply も destroy も行わないこと
を確認する。
"""

from src import commands
from src.config import Config

RDS = "module.database.aws_db_instance.this"


def _dummy_cfg():
    return Config("bucket", "us-east-1", "acct", "prefix", "database/state.tfstate", "app/state.tfstate", {})


def _wire(monkeypatch, calls, state):
    monkeypatch.setattr(commands.config, "load_config", lambda *a, **k: _dummy_cfg())
    monkeypatch.setattr(commands, "prerequisites", lambda *a, **k: None)
    monkeypatch.setattr(commands.aws, "object_exists", lambda *a, **k: False)
    monkeypatch.setattr(commands.prompts, "confirm_typed", lambda *a, **k: None)
    monkeypatch.setattr(commands.tf, "init_backend", lambda *a, **k: None)
    monkeypatch.setattr(commands.tf, "state_list", lambda *a, **k: list(state))

    def _apply(cwd, targets=None, variables=None, what=""):
        calls.append(("apply", targets, variables))

    def _destroy(cwd, variables=None, what=""):
        calls.append(("destroy", None, variables))

    monkeypatch.setattr(commands.tf, "apply", _apply)
    monkeypatch.setattr(commands.tf, "destroy", _destroy)


def test_rds_present_applies_only_rds_target_then_destroys(monkeypatch):
    calls = []
    _wire(monkeypatch, calls, [RDS, "module.network.aws_security_group.rds"])

    commands.cmd_destroy_database()

    assert [c[0] for c in calls] == ["apply", "destroy"]
    assert calls[0][1] == [RDS]
    assert calls[0][2] == {"deletion_protection": "false"}
    assert calls[1][2] == {"deletion_protection": "false", "skip_final_snapshot": "true"}


def test_rds_absent_skips_apply_and_destroys(monkeypatch):
    calls = []
    _wire(monkeypatch, calls, ["module.network.aws_security_group.rds", "module.ecr.aws_ecr_repository.this"])

    commands.cmd_destroy_database()

    assert [c[0] for c in calls] == ["destroy"]


def test_empty_state_does_nothing(monkeypatch):
    calls = []
    _wire(monkeypatch, calls, [])

    commands.cmd_destroy_database()

    assert calls == []
