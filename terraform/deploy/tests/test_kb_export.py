"""CSV スナップショットの書き出し（ADR-0109 段階 1）の cmd_kb_export / _fetch_snapshot を検証する。

実 AWS / terraform / dvc には触れず、aws / tf / proc / prompts / config をスタブする。リポジトリルートは
tmp_path/repo とし（TERRAFORM_ROOT=tmp_path/repo/terraform）、スナップショットをその下に置く。
"""

import hashlib
import json

import pytest

from src import commands
from src.config import Config
from src.errors import DeployError

ACCOUNT = "123456789012"
TABLES = {"knowledge": ["hiroba_category", "tag"], "conversation": ["conversation"]}


def _csv(label, table):
    return f'"id","name"\n"1","{label}-{table}"\n'.encode("utf-8")


def _remote(*, broken=None):
    """S3 上のスナップショット（{key 末尾: bytes}）とマニフェストを作る。broken=(label, table) はハッシュを狂わせる。"""
    files, databases = {}, {}
    for label, tables in TABLES.items():
        entries = {}
        for table in tables:
            data = _csv(label, table)
            files[f"{label}/{table}.csv"] = data
            digest = hashlib.sha256(data).hexdigest()
            if broken == (label, table):
                digest = "0" * 64
            entries[table] = {"file": f"{table}.csv", "rows": 1, "columns": ["id", "name"], "bytes": len(data), "sha256": digest}
        databases[label] = {
            "tables": entries,
            "schema_version": ["0001"],
            "snapshot_sha256": commands._snapshot_sha256(
                {t: hashlib.sha256(_csv(label, t)).hexdigest() for t in tables}
            ),
        }
    manifest = {"format": 2, "adr": "ADR-0109", "kind": "snapshot", "created_at": "t", "timestamp": "ts", "databases": databases}
    return files, manifest


@pytest.fixture
def wired(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / "terraform").mkdir(parents=True)
    calls = []
    state = {"remote": _remote()}
    monkeypatch.setenv("TERRAFORM_ROOT", str(repo / "terraform"))
    monkeypatch.setattr(commands.config, "load_config", lambda *a, **k: Config("b", "us-east-1", ACCOUNT, "p", "d", "a", {}))
    monkeypatch.setattr(commands, "prerequisites", lambda *a, **k: None)
    monkeypatch.setattr(commands.prompts, "confirm_or_exit", lambda *a, **k: calls.append(("yn",)))
    monkeypatch.setattr(
        commands, "_export_context",
        lambda cfg, batch: commands._ExportContext("cluster", "app", ["s"], "sg", "db-init", "bucket"),
    )
    monkeypatch.setattr(commands.aws, "account_id", lambda: ACCOUNT)
    monkeypatch.setattr(commands.gitinfo, "current", lambda: commands.gitinfo.GitInfo("abc", False))
    monkeypatch.setattr(commands.aws, "service_desired_count", lambda c, s, r: 1)
    monkeypatch.setattr(commands.aws, "set_service_desired_count", lambda c, s, n, r: calls.append(("set", n)))
    monkeypatch.setattr(commands.aws, "wait_services_stable", lambda *a, **k: None)

    def _run_task(cluster, family, subnets, sg, region, container_name, environment):
        calls.append(("task", environment["EXPORT_FORMAT"], environment["EXPORT_PREFIX"]))
        return "arn"

    monkeypatch.setattr(commands.aws, "run_import_task", _run_task)
    monkeypatch.setattr(commands.aws, "wait_task_stopped", lambda *a, **k: {})
    monkeypatch.setattr(commands.aws, "get_task_log_events", lambda *a, **k: [])
    monkeypatch.setattr(commands.aws, "task_exit_code", lambda t: "0")

    def _download(bucket, key, path, region):
        files, manifest = state["remote"]
        tail = key.split("/", 2)[2]  # snapshot/<ts>/<tail>
        data = json.dumps(manifest).encode("utf-8") if tail == "manifest.json" else files[tail]
        with open(path, "wb") as f:
            f.write(data)

    monkeypatch.setattr(commands.aws, "download_file", _download)
    monkeypatch.setattr(commands.proc, "run", lambda cmd, cwd=None, what=None: calls.append(("run", cmd)))
    return calls, state, repo


def test_kb_export_places_snapshots_and_runs_dvc_add(wired):
    calls, _state, repo = wired
    knowledge = repo / "db_init" / "data" / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "stale.csv").write_text("old", encoding="utf-8")  # 前回の版は置き換わる

    commands.cmd_kb_export(assume_yes=True)

    assert ("task", "csv", "snapshot") in calls
    assert sorted(p.name for p in knowledge.iterdir()) == ["hiroba_category.csv", "manifest.json", "tag.csv"]
    assert (knowledge / "tag.csv").read_bytes() == _csv("knowledge", "tag")
    own = json.loads((knowledge / "manifest.json").read_text(encoding="utf-8"))
    assert list(own["databases"]) == ["knowledge"]
    assert own["environment"]["aws_account_id"] == ACCOUNT
    conversation = repo / "snapshots" / "conversation"
    assert (conversation / "conversation.csv").is_file()
    assert not (repo / "snapshots" / ".incoming").exists()
    assert ("run", ["dvc", "add", "db_init/data/knowledge", "snapshots/conversation"]) in calls
    assert calls.count(("set", 1)) == 1  # 集約サービスを元に戻した


def test_kb_export_rejects_hash_mismatch_and_keeps_previous(wired):
    calls, state, repo = wired
    state["remote"] = _remote(broken=("knowledge", "tag"))
    knowledge = repo / "db_init" / "data" / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "keep.csv").write_text("previous", encoding="utf-8")

    with pytest.raises(DeployError, match="SHA-256"):
        commands.cmd_kb_export(assume_yes=True)

    assert (knowledge / "keep.csv").read_text(encoding="utf-8") == "previous"
    assert not any(c[0] == "run" for c in calls)  # dvc add しない
    assert ("set", 1) in calls  # 失敗しても集約サービスは元に戻す
