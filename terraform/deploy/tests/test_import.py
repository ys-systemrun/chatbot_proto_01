"""全データインポート（ADR-0066）の cmd_import_data を検証する。

実 AWS には触れず、aws / tf / prompts / config をスタブし、
「ダンプアップロード → サービス停止 → IMPORT_MODE run-task → サービス再開」の順序と、
失敗時でもサービスが停止前の desired_count へ復元されることを確認する。
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
        "import_bucket_name": "prefix-import-acct-us-east-1",
        "cluster_name": "prefix-cluster",
    }[name]


def _wire_common(monkeypatch, calls, *, exit_code="0"):
    monkeypatch.setattr(commands.config, "load_config", lambda *a, **k: _dummy_cfg())
    monkeypatch.setattr(commands, "prerequisites", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_require_database_applied", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_require_app_applied", lambda *a, **k: None)
    monkeypatch.setattr(commands.os.path, "isfile", lambda p: True)
    monkeypatch.setattr(commands.prompts, "confirm_typed", lambda *a, **k: None)

    monkeypatch.setattr(commands.tf, "init_backend", lambda *a, **k: None)
    monkeypatch.setattr(commands.tf, "output_json", lambda *a, **k: ["subnet-1"])
    monkeypatch.setattr(commands.tf, "output_raw", _output_raw)

    monkeypatch.setattr(
        commands.aws, "upload_file", lambda b, k, p, r: calls.append(("upload", k))
    )
    monkeypatch.setattr(commands.aws, "service_desired_count", lambda c, s, r: 1)
    monkeypatch.setattr(
        commands.aws,
        "set_service_desired_count",
        lambda c, s, count, r: calls.append(("set", s, count)),
    )
    monkeypatch.setattr(
        commands.aws, "wait_services_stable", lambda c, s, r: calls.append(("stable", tuple(s)))
    )

    def _run_import_task(cluster, family, subnets, sg, region, container_name, environment):
        calls.append(("run", environment.get("IMPORT_MODE"), environment.get("IMPORT_TARGET")))
        return "task-arn"

    monkeypatch.setattr(commands.aws, "run_import_task", _run_import_task)
    monkeypatch.setattr(commands.aws, "wait_task_stopped", lambda *a, **k: {"containers": []})
    monkeypatch.setattr(commands.aws, "task_exit_code", lambda t: exit_code)


def test_import_both_orders_stop_run_restart(monkeypatch):
    calls = []
    _wire_common(monkeypatch, calls)

    commands.cmd_import_data(target="both")

    names = [c[0] for c in calls]
    # アップロード（2ダンプ）→ 停止（set 0）→ run → 再開（set 1）の順。
    assert names.count("upload") == 2
    run_idx = names.index("run")
    set_zeros = [i for i, c in enumerate(calls) if c[0] == "set" and c[2] == 0]
    set_restore = [i for i, c in enumerate(calls) if c[0] == "set" and c[2] == 1]
    assert set_zeros and set_restore
    assert max(set_zeros) < run_idx < min(set_restore)  # 停止→run→再開
    # both は chatbot 側の3サービスを停止対象にする。
    stopped = {c[1] for c in calls if c[0] == "set" and c[2] == 0}
    assert stopped == {"admin_ui", "knowledge_mcp", "tag_selector_mcp"}
    # run-task は IMPORT_MODE=true / target=both を渡す。
    run_call = next(c for c in calls if c[0] == "run")
    assert run_call[1] == "true" and run_call[2] == "both"


def test_import_conversation_only_stops_admin_ui(monkeypatch):
    calls = []
    _wire_common(monkeypatch, calls)

    commands.cmd_import_data(target="conversation")

    stopped = {c[1] for c in calls if c[0] == "set" and c[2] == 0}
    assert stopped == {"admin_ui"}
    assert [c for c in calls if c[0] == "upload"] == [("upload", "import/conversation.sql")]


def test_import_restarts_services_on_failure(monkeypatch):
    calls = []
    _wire_common(monkeypatch, calls, exit_code="1")  # 異常終了 → DeployError

    with pytest.raises(commands.DeployError):
        commands.cmd_import_data(target="chatbot")

    # 失敗しても停止したサービスは元の desired_count(=1) へ復元される。
    restored = {c[1] for c in calls if c[0] == "set" and c[2] == 1}
    assert restored == {"admin_ui", "knowledge_mcp", "tag_selector_mcp"}
