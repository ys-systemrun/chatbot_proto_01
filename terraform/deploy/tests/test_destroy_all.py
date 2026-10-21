"""退避付き一括破棄（ADR-0103）の cmd_destroy_all / cmd_export_data / import-data のスキーマ照合を検証する。

実 AWS / terraform には触れず、aws / tf / prompts / config をスタブする。退避ファイルは
TERRAFORM_ROOT を tmp_path に向けて、tmp_path/backup/ に作る。
"""

import hashlib
import json

import pytest

from src import commands
from src.config import Config
from src.errors import DeployError

ACCOUNT = "123456789012"


def _cfg():
    return Config("bucket", "us-east-1", ACCOUNT, "prefix", "database/state.tfstate", "app/state.tfstate", {})


def _sql(label):
    return f"-- {label}\nTRUNCATE x;\n".encode("utf-8")


def _manifest(*, with_env=True, schema=("0001",)):
    m = {
        "format": 1,
        "created_at": "2026-10-21T10:00:00+09:00",
        "databases": {
            label: {
                "file": f"{label}.sql",
                "bytes": len(_sql(label)),
                "sha256": hashlib.sha256(_sql(label)).hexdigest(),
                "tables": {"t": 3},
                "schema_version": list(schema),
            }
            for label in ("knowledge", "conversation")
        },
    }
    if with_env:
        m["environment"] = {"aws_account_id": ACCOUNT, "aws_region": "us-east-1", "cluster": "prefix-cluster"}
    return m


def _write_backup(directory, manifest=None):
    directory.mkdir(parents=True, exist_ok=True)
    for label in ("knowledge", "conversation"):
        (directory / f"{label}.sql").write_bytes(_sql(label))
    (directory / "manifest.json").write_text(json.dumps(manifest or _manifest()), encoding="utf-8")


def _outputs(_cwd, name):
    return {
        "cluster_name": "prefix-cluster",
        "app_service_name": "prefix-app",
        "sg_verification_task_id": "sg-1",
        "db_init_task_family": "db-init",
        "import_bucket_name": "prefix-import",
    }[name]


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """共通のスタブ。calls に操作を記録し、state の有無・失敗させる段を state で切り替える。"""
    calls = []
    state = {"database": True, "app": True, "export_exit": "0", "fail": set()}
    monkeypatch.setenv("TERRAFORM_ROOT", str(tmp_path))
    monkeypatch.setattr(commands.config, "load_config", lambda *a, **k: _cfg())
    monkeypatch.setattr(commands, "prerequisites", lambda *a, **k: None)
    monkeypatch.setattr(commands.prompts, "confirm_typed", lambda prompt, expected: calls.append(("confirm", expected)))
    monkeypatch.setattr(commands.prompts, "confirm_or_exit", lambda *a, **k: calls.append(("yn",)))

    monkeypatch.setattr(commands.aws, "object_exists", lambda b, key: True)
    monkeypatch.setattr(commands.aws, "account_id", lambda: ACCOUNT)
    monkeypatch.setattr(commands.tf, "init_backend", lambda *a, **k: None)

    def _state_list(cwd):
        layer = "app" if cwd.name == "app" else "database"
        return ["x"] if state[layer] else []

    monkeypatch.setattr(commands.tf, "state_list", _state_list)
    monkeypatch.setattr(commands.tf, "output_raw", _outputs)
    monkeypatch.setattr(commands.tf, "output_json", lambda *a, **k: ["subnet-1"])
    monkeypatch.setattr(commands.gitinfo, "current", lambda: commands.gitinfo.GitInfo("abc", False))

    monkeypatch.setattr(commands.aws, "service_desired_count", lambda c, s, r: 1)
    monkeypatch.setattr(
        commands.aws, "set_service_desired_count", lambda c, s, n, r: calls.append(("set", n))
    )
    monkeypatch.setattr(commands.aws, "wait_services_stable", lambda *a, **k: None)

    def _run_task(cluster, family, subnets, sg, region, container_name, environment):
        calls.append(("export", environment.get("EXPORT_MANIFEST_ONLY") == "true"))
        state["last_ts"] = environment["EXPORT_TIMESTAMP"]
        return "task-arn"

    monkeypatch.setattr(commands.aws, "run_import_task", _run_task)
    monkeypatch.setattr(commands.aws, "wait_task_stopped", lambda *a, **k: {})
    monkeypatch.setattr(commands.aws, "get_task_log_events", lambda *a, **k: [])
    monkeypatch.setattr(commands.aws, "task_exit_code", lambda t: state["export_exit"])

    def _download(bucket, key, path, region):
        name = key.rsplit("/", 1)[-1]
        if name == "manifest.json":
            data = json.dumps(state.get("remote_manifest") or _manifest(with_env=False)).encode("utf-8")
        else:
            data = state.get("remote_sql", {}).get(name) or _sql(name[:-4])
        with open(path, "wb") as f:
            f.write(data)

    monkeypatch.setattr(commands.aws, "download_file", _download)

    def _destroy_app(confirm=True):
        calls.append(("destroy-app", confirm))
        if "destroy-app" in state["fail"]:
            raise DeployError("app destroy failed")

    def _destroy_database(confirm=True):
        calls.append(("destroy-database", confirm))
        if "destroy-database" in state["fail"]:
            raise DeployError("database destroy failed")

    monkeypatch.setattr(commands, "cmd_destroy_app", _destroy_app)
    monkeypatch.setattr(commands, "cmd_destroy_database", _destroy_database)
    return calls, state, tmp_path / "backup"


def _names(calls):
    return [c[0] for c in calls]


# --- 通常実行 -------------------------------------------------------------------

def test_destroy_all_exports_then_destroys_in_order(wired):
    calls, _, backup = wired

    commands.cmd_destroy_all()

    assert _names(calls) == ["confirm", "set", "export", "destroy-app", "destroy-database"]
    assert calls[0] == ("confirm", "destroy-all")
    assert ("set", 0) in calls and ("set", 1) not in calls  # 成功時はサービスを戻さない（直後に破棄）
    assert calls[3] == ("destroy-app", False) and calls[4] == ("destroy-database", False)
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["environment"]["aws_account_id"] == ACCOUNT
    assert not (backup / ".incoming").exists()


def test_export_failure_destroys_nothing_and_restores_service(wired):
    calls, state, _ = wired
    state["export_exit"] = "1"

    with pytest.raises(DeployError):
        commands.cmd_destroy_all()

    assert "destroy-app" not in _names(calls) and "destroy-database" not in _names(calls)
    assert ("set", 1) in calls  # 失敗時は停止前の desired_count へ戻す


def test_sha_mismatch_keeps_previous_backup_and_destroys_nothing(wired):
    calls, state, backup = wired
    _write_backup(backup)
    before = (backup / "knowledge.sql").read_bytes()
    state["remote_sql"] = {"knowledge.sql": b"tampered"}

    with pytest.raises(DeployError, match="SHA-256"):
        commands.cmd_destroy_all()

    assert "destroy-app" not in _names(calls)
    assert (backup / "knowledge.sql").read_bytes() == before  # 前回分は上書きされない


def test_destroy_app_failure_skips_database_and_shows_resume(wired):
    calls, state, _ = wired
    state["fail"] = {"destroy-app"}

    with pytest.raises(DeployError, match="--resume-from destroy-app"):
        commands.cmd_destroy_all()

    assert "destroy-database" not in _names(calls)


def test_no_app_construction_stops_with_guidance(wired):
    calls, state, _ = wired
    state["app"] = False

    with pytest.raises(DeployError, match="destroy-database.bat"):
        commands.cmd_destroy_all()

    assert calls == []  # 確認も退避も破棄も行わない


def test_empty_database_state_does_nothing(wired):
    calls, state, _ = wired
    state["database"] = False

    commands.cmd_destroy_all()

    assert calls == []


# --- 再開実行 -------------------------------------------------------------------

def test_resume_from_destroy_app_skips_export(wired):
    calls, _, backup = wired
    _write_backup(backup)

    commands.cmd_destroy_all(resume_from="destroy-app")

    assert _names(calls) == ["confirm", "destroy-app", "destroy-database"]


def test_resume_from_destroy_database_runs_only_database(wired):
    calls, state, backup = wired
    _write_backup(backup)
    state["app"] = False

    commands.cmd_destroy_all(resume_from="destroy-database")

    assert _names(calls) == ["confirm", "destroy-database"]


def test_resume_with_tampered_backup_destroys_nothing(wired):
    calls, _, backup = wired
    _write_backup(backup)
    (backup / "conversation.sql").write_bytes(b"changed")

    with pytest.raises(DeployError, match="SHA-256"):
        commands.cmd_destroy_all(resume_from="destroy-app")

    assert calls == []


def test_resume_with_other_account_destroys_nothing(wired):
    calls, _, backup = wired
    manifest = _manifest()
    manifest["environment"]["aws_account_id"] = "999999999999"
    _write_backup(backup, manifest)

    with pytest.raises(DeployError, match="環境が現在の .env と一致しません"):
        commands.cmd_destroy_all(resume_from="destroy-app")

    assert calls == []


def test_resume_from_database_while_app_remains_is_refused(wired):
    calls, _, backup = wired
    _write_backup(backup)

    with pytest.raises(DeployError, match="--resume-from destroy-app"):
        commands.cmd_destroy_all(resume_from="destroy-database")

    assert calls == []


def test_resume_from_app_when_app_already_gone_is_refused(wired):
    _, state, backup = wired
    _write_backup(backup)
    state["app"] = False

    with pytest.raises(DeployError, match="--resume-from destroy-database"):
        commands.cmd_destroy_all(resume_from="destroy-app")


# --- export-data ---------------------------------------------------------------

def test_export_data_overwrites_previous_backup_and_restores_service(wired):
    calls, _, backup = wired
    _write_backup(backup, {**_manifest(), "created_at": "old"})

    commands.cmd_export_data(assume_yes=True)

    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["created_at"] != "old"
    assert ("set", 0) in calls and ("set", 1) in calls  # 成功時も元へ戻す
    assert sorted(p.name for p in backup.iterdir()) == ["conversation.sql", "knowledge.sql", "manifest.json"]


# --- import-data のスキーマ照合 ---------------------------------------------------

def test_schema_diff():
    assert commands.schema_diff(["a", "b"], ["b", "c"]) == (["a"], ["c"])
    assert commands.schema_diff(["a"], ["a"]) == ([], [])


def test_matching_schema_does_not_ask(monkeypatch):
    asked = []
    monkeypatch.setattr(commands.prompts, "confirm_or_exit", lambda *a, **k: asked.append(k))

    commands._confirm_schema_versions(["knowledge"], {"knowledge": ["1", "2"]}, {"knowledge": ["2", "1"]})

    assert asked == []


def test_different_or_unknown_schema_asks_without_bypass(monkeypatch):
    asked = []
    monkeypatch.setattr(commands.prompts, "confirm_or_exit", lambda *a, **k: asked.append(k))

    commands._confirm_schema_versions(["knowledge"], {"knowledge": ["1"]}, {"knowledge": ["1", "2"]})
    commands._confirm_schema_versions(["conversation"], {"conversation": None}, None)

    assert asked == [{"assume_yes": False}, {"assume_yes": False}]


def test_dump_schema_version_reads_manifest_next_to_dump(tmp_path):
    _write_backup(tmp_path, _manifest(schema=("0001", "0002")))

    assert commands._dump_schema_version(str(tmp_path / "knowledge.sql"), "knowledge") == ["0001", "0002"]
    assert commands._dump_schema_version(str(tmp_path / "nope" / "knowledge.sql"), "knowledge") is None
