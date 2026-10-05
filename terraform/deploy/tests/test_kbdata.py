"""kbdata（ADR-0097: DVC 管理のシード元データの取得・検証・版の算出）を検証する。

dvc / git は実行せず proc をスタブし、
- dvc pull → dvc status の順に呼び、一致していれば情報源ごとの md5 と commit を版として返すこと
- dvc status が差分を返したらビルド前に DeployError で止めること
- dvc pull の失敗を push し忘れの可能性を示す DeployError にすること
- .dvc が1つも無ければ DeployError にすること
を確認する。
"""

import json

import pytest

from src import kbdata
from src.errors import DeployError

HIROBA_DVC = """outs:
- md5: 98eb662a043a02f3d521f55ba1140a62.dir
  size: 2194418
  nfiles: 5
  hash: md5
  path: hiroba_qa
"""
TS_DVC = """outs:
- md5: 55537b51dd84d989d04b85e0d6a429c8.dir
  size: 197672
  nfiles: 2
  hash: md5
  path: troubleshooting
"""


def _repo(tmp_path, with_dvc=True):
    data = tmp_path / "db_init" / "data"
    data.mkdir(parents=True)
    if with_dvc:
        (data / "hiroba_qa.dvc").write_text(HIROBA_DVC, encoding="utf-8")
        (data / "troubleshooting.dvc").write_text(TS_DVC, encoding="utf-8")
    return tmp_path


def _wire(monkeypatch, calls, *, status=None, pull_fails=False, dirty=""):
    def _run(cmd, cwd=None, what=None, input_text=None):
        calls.append(tuple(cmd[:2]))
        if pull_fails and cmd[:2] == ["dvc", "pull"]:
            raise DeployError("dvc pull が失敗しました (exit 1)")

    def _capture(cmd, cwd=None, what=None):
        calls.append(tuple(cmd[:2]))
        if cmd[:2] == ["dvc", "status"]:
            return json.dumps(status or {})
        if cmd[:2] == ["git", "rev-parse"]:
            return "abc123\n"
        if cmd[:2] == ["git", "status"]:
            return dirty
        raise AssertionError(cmd)

    monkeypatch.setattr(kbdata.proc, "run", _run)
    monkeypatch.setattr(kbdata.proc, "capture", _capture)


def test_prepare_returns_version_when_clean(monkeypatch, tmp_path):
    calls = []
    _wire(monkeypatch, calls)

    version = kbdata.prepare(_repo(tmp_path))

    assert calls[:2] == [("dvc", "pull"), ("dvc", "status")]
    assert version.sources == {
        "hiroba_qa": "98eb662a043a02f3d521f55ba1140a62",
        "troubleshooting": "55537b51dd84d989d04b85e0d6a429c8",
    }
    assert version.git_commit == "abc123"
    assert version.env_value() == (
        "hiroba_qa=98eb662a043a02f3d521f55ba1140a62,troubleshooting=55537b51dd84d989d04b85e0d6a429c8"
    )
    assert version.labels() == {
        "org.opencontainers.image.revision": "abc123",
        "kb.data.hiroba_qa.md5": "98eb662a043a02f3d521f55ba1140a62",
        "kb.data.troubleshooting.md5": "55537b51dd84d989d04b85e0d6a429c8",
    }


def test_prepare_stops_when_workspace_differs(monkeypatch, tmp_path):
    calls = []
    _wire(monkeypatch, calls, status={"db_init/data/hiroba_qa.dvc": [{"changed outs": {"hiroba_qa": "modified"}}]})

    with pytest.raises(DeployError, match="一致しません"):
        kbdata.prepare(_repo(tmp_path))


def test_prepare_explains_missing_push(monkeypatch, tmp_path):
    calls = []
    _wire(monkeypatch, calls, pull_fails=True)

    with pytest.raises(DeployError, match="dvc.bat push"):
        kbdata.prepare(_repo(tmp_path))


def test_prepare_requires_dvc_files(monkeypatch, tmp_path):
    calls = []
    _wire(monkeypatch, calls)

    with pytest.raises(DeployError, match=r"\.dvc ファイルがありません"):
        kbdata.prepare(_repo(tmp_path, with_dvc=False))
    assert calls == []
