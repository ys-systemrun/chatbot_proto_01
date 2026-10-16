"""デプロイするコードの版（git commit と未コミット変更の有無）の取得（ADR-0099 §1）。

agent_invitro のリリース（release_id）の要素として、イメージのラベルとタスク環境変数
（GIT_COMMIT / GIT_DIRTY）に渡す。dirty は「デプロイされる内容がコミットと一致しない」ことを表すため、
次は判定の対象外とする:
  - 未追跡ファイル（作業メモ等）
  - DIRTY_EXCLUDES のパス（評価データ・文書）。evals/history.csv は評価のたびに書き換わるため、
    これを含めると評価結果をコミットする前のデプロイが毎回 dirty になる
改行コードの差は deploy イメージの core.autocrlf=true で吸収する（terraform/deploy/Dockerfile）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import paths, proc

# git_dirty の判定から外すパス（デプロイされるイメージ・設定に入らないもの）。
DIRTY_EXCLUDES = ("evals", "docs")


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
    pathspec = ["--", "."] + [f":(exclude){p}" for p in DIRTY_EXCLUDES]
    changes = proc.capture(
        ["git", "status", "--porcelain", "--untracked-files=no", *pathspec], cwd=repo, what="git status"
    ).strip()
    return GitInfo(commit=commit, dirty=bool(changes))
