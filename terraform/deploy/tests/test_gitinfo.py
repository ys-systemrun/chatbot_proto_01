"""gitinfo（ADR-0099 §1 の GIT_COMMIT / GIT_DIRTY）を検証する（git は実行しない）。"""

from src import gitinfo


def _wire(monkeypatch, status_output, calls):
    def _capture(cmd, cwd=None, what=None):
        calls.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return "abc123\n"
        return status_output

    monkeypatch.setattr(gitinfo.proc, "capture", _capture)


def test_clean_tree_is_not_dirty_and_excludes_eval_data_and_docs(monkeypatch, tmp_path):
    calls = []
    _wire(monkeypatch, "", calls)

    info = gitinfo.current(tmp_path)

    assert (info.commit, info.dirty) == ("abc123", False)
    status = calls[1]
    assert status[:4] == ["git", "status", "--porcelain", "--untracked-files=no"]
    assert status[4:] == ["--", ".", ":(exclude)evals", ":(exclude)docs"]
    assert info.env() == {"GIT_COMMIT": "abc123", "GIT_DIRTY": "false"}


def test_tracked_code_change_is_dirty(monkeypatch, tmp_path):
    _wire(monkeypatch, " M agent_invitro/prompts/generate.md\n", [])

    info = gitinfo.current(tmp_path)

    assert info.dirty is True
    assert info.labels() == {"org.opencontainers.image.revision": "abc123", "git.dirty": "true"}
