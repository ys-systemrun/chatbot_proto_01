"""デプロイするコードの版（git commit と未コミット変更の有無）の取得（ADR-0099 §1）。

agent_invitro のリリース（release_id）の要素として、イメージのラベルとタスク環境変数
（GIT_COMMIT / GIT_DIRTY）に渡す。未追跡ファイル（作業メモ等）は版に影響しないため対象外とし、
追跡済みファイルの変更だけを dirty とみなす。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import paths, proc


@dataclass
class GitInfo:
    commit: str
    dirty: bool

    def env(self) -> dict[str, str]:
        return {"GIT_COMMIT": self.commit, "GIT_DIRTY": "true" if self.dirty else "false"}

    def labels(self) -> dict[str, str]:
        return {"org.opencontainers.image.revision": self.commit, "git.dirty": str(self.dirty).lower()}


def current(repo: Path | None = None) -> GitInfo:
    repo = repo or paths.repo_root()
    commit = proc.capture(["git", "rev-parse", "HEAD"], cwd=repo, what="git rev-parse").strip()
    changes = proc.capture(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo, what="git status"
    ).strip()
    return GitInfo(commit=commit, dirty=bool(changes))
