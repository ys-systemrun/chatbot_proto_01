"""DVC で管理するナレッジデータ（シード元データ）の取得・検証・版の算出（ADR-0097）。

db_init イメージを build する直前に呼び、次を保証する:
  1. db_init/data/*.dvc が指すデータを DVC リモート（S3）から取得する（dvc pull）。
  2. ワークスペースのデータが .dvc と一致している（dvc add していない編集が無い）。
  3. 情報源ごとの md5 と git commit を「版」として返し、イメージのラベル・タスク環境変数に残す。
どれかを満たせない場合は DeployError でビルド前に止め、版を特定できないデータをデプロイしない。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import log, paths, proc
from .errors import DeployError

_MD5_RE = re.compile(r"^\s*-?\s*md5:\s*([0-9a-f]{32})(?:\.dir)?\s*$", re.MULTILINE)


@dataclass
class KbDataVersion:
    sources: dict[str, str]  # 情報源名（.dvc のファイル名）-> md5
    git_commit: str

    def env_value(self) -> str:
        """タスク環境変数 KB_DATA_VERSION の値（例: hiroba_qa=<md5>,troubleshooting=<md5>）。"""
        return ",".join(f"{name}={md5}" for name, md5 in sorted(self.sources.items()))

    def labels(self) -> dict[str, str]:
        result = {"org.opencontainers.image.revision": self.git_commit}
        for name, md5 in sorted(self.sources.items()):
            result[f"kb.data.{name}.md5"] = md5
        return result


def dvc_files(data_dir: Path | None = None) -> list[Path]:
    data_dir = data_dir or paths.kb_data_dir()
    files = sorted(data_dir.glob("*.dvc"))
    if not files:
        raise DeployError(
            f"{data_dir} に .dvc ファイルがありません（シード元データが DVC 管理されていません）。\n"
            "  terraform\\dvc.bat add db_init/data/<情報源> → dvc.bat push を先に実行してください（ADR-0097）。"
        )
    return files


def read_md5(dvc_file: Path) -> str:
    match = _MD5_RE.search(dvc_file.read_text(encoding="utf-8"))
    if not match:
        raise DeployError(f"{dvc_file} から md5 を読み取れません。")
    return match.group(1)


def prepare(repo: Path | None = None) -> KbDataVersion:
    """dvc pull → dvc status で一致確認 → 版を返す。"""
    repo = repo or paths.repo_root()
    files = dvc_files(repo / "db_init" / "data")
    targets = [str(f.relative_to(repo)).replace("\\", "/") for f in files]

    log.step("ナレッジデータの取得（dvc pull, ADR-0097）")
    try:
        proc.run(["dvc", "pull", *targets], cwd=repo, what="dvc pull")
    except DeployError as exc:
        raise DeployError(
            f"{exc}\n  DVC リモートにデータの実体がない可能性があります。"
            "データを追加した人が dvc.bat push を実行済みか確認してください。"
        ) from exc

    log.step("ナレッジデータの一致確認（dvc status）")
    status_out = proc.capture(["dvc", "status", "--json", *targets], cwd=repo, what="dvc status").strip()
    status = json.loads(status_out) if status_out else {}
    if status:
        raise DeployError(
            "ワークスペースのナレッジデータが .dvc と一致しません（dvc add していない編集があります）:\n"
            f"  {json.dumps(status, ensure_ascii=False)}\n"
            "  意図した変更なら dvc.bat add → git commit → dvc.bat push の後に再実行してください。"
            " 破棄するなら dvc.bat checkout で .dvc の版に戻せます。"
        )

    sources = {f.stem: read_md5(f) for f in files}
    commit = proc.capture(["git", "rev-parse", "HEAD"], cwd=repo, what="git rev-parse").strip()
    dirty = proc.capture(["git", "status", "--porcelain", "--", *targets], cwd=repo, what="git status").strip()
    if dirty:
        log.warn(
            "未コミットの .dvc ファイルがあります。このデータの版は git の履歴から辿れません"
            "（デプロイ後に .dvc をコミットしてください）:\n" + dirty
        )

    version = KbDataVersion(sources=sources, git_commit=commit)
    for name, md5 in sorted(sources.items()):
        log.ok(f"{name}: {md5}")
    return version
