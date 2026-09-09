"""アドホック SQL 実行（ADR-0083）の cmd_query を検証する。

実 AWS には触れず、aws / tf / prompts / config をスタブし、
- QUERY_MODE=true / QUERY_TARGET_DB / QUERY_SQL の environment オーバーライドで run-task を起動すること
- 実行前に対象DB名のタイプ確認（confirm_typed）を必ず呼ぶこと
- タスク終了後に CloudWatch Logs（get_task_log_events）を取得して表示すること
- 異常終了（exitCode!=0）で DeployError になること
- 不正な --target / 空・不在の query.sql で DeployError になること
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


def _write_sql(tmp_path, text="SELECT 1;"):
    p = tmp_path / "query.sql"
    p.write_text(text, encoding="utf-8")
    return str(p)


def _wire_common(monkeypatch, calls, *, exit_code="0", confirm_target=None):
    monkeypatch.setattr(commands.config, "load_config", lambda *a, **k: _dummy_cfg())
    monkeypatch.setattr(commands, "prerequisites", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_require_database_applied", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_require_app_applied", lambda *a, **k: None)

    monkeypatch.setattr(commands.tf, "init_backend", lambda *a, **k: None)
    monkeypatch.setattr(commands.tf, "output_json", lambda *a, **k: ["subnet-1"])
    monkeypatch.setattr(commands.tf, "output_raw", _output_raw)

    def _confirm_typed(prompt, expected):
        calls.append(("confirm", expected))

    monkeypatch.setattr(commands.prompts, "confirm_typed", _confirm_typed)

    def _run_import_task(cluster, family, subnets, sg, region, container_name, environment):
        calls.append((
            "run",
            environment.get("QUERY_MODE"),
            environment.get("QUERY_TARGET_DB"),
            environment.get("QUERY_SQL"),
        ))
        return "arn:aws:ecs:...:task/prefix-cluster/abc123"

    monkeypatch.setattr(commands.aws, "run_import_task", _run_import_task)
    monkeypatch.setattr(commands.aws, "wait_task_stopped", lambda *a, **k: {"containers": []})
    monkeypatch.setattr(commands.aws, "task_exit_code", lambda t: exit_code)

    def _get_logs(log_group, stream_prefix, container_name, task_arn, region):
        calls.append(("logs", log_group, task_arn))
        return ["col", "1"]

    monkeypatch.setattr(commands.aws, "get_task_log_events", _get_logs)


def test_query_sets_query_mode_override_and_confirms(monkeypatch, tmp_path):
    calls = []
    _wire_common(monkeypatch, calls)
    sql = _write_sql(tmp_path, "SELECT 1;")

    commands.cmd_query(target="chatbot", sql_file=sql)

    # confirm_typed（対象DB名）→ run（QUERY_MODE=true）→ logs 取得の順。
    names = [c[0] for c in calls]
    assert names == ["confirm", "run", "logs"]
    assert calls[0] == ("confirm", "chatbot")
    run = calls[1]
    assert run[1] == "true" and run[2] == "chatbot" and run[3] == "SELECT 1;"
    assert calls[2][1] == "/ecs/db-hiroba-qa-init"


def test_query_target_both(monkeypatch, tmp_path):
    calls = []
    _wire_common(monkeypatch, calls)
    sql = _write_sql(tmp_path)

    commands.cmd_query(target="both", sql_file=sql)

    assert ("confirm", "both") in calls
    run = next(c for c in calls if c[0] == "run")
    assert run[2] == "both"


def test_query_raises_on_nonzero_exit(monkeypatch, tmp_path):
    calls = []
    _wire_common(monkeypatch, calls, exit_code="1")
    sql = _write_sql(tmp_path)

    with pytest.raises(commands.DeployError):
        commands.cmd_query(target="chatbot", sql_file=sql)


def test_query_invalid_target(monkeypatch, tmp_path):
    calls = []
    _wire_common(monkeypatch, calls)
    with pytest.raises(commands.DeployError):
        commands.cmd_query(target="nope", sql_file=_write_sql(tmp_path))


def test_query_missing_file(monkeypatch, tmp_path):
    calls = []
    _wire_common(monkeypatch, calls)
    with pytest.raises(commands.DeployError):
        commands.cmd_query(target="chatbot", sql_file=str(tmp_path / "nope.sql"))


def test_query_empty_file(monkeypatch, tmp_path):
    calls = []
    _wire_common(monkeypatch, calls)
    with pytest.raises(commands.DeployError):
        commands.cmd_query(target="chatbot", sql_file=_write_sql(tmp_path, "   \n"))
