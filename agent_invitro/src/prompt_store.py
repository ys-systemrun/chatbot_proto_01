"""プロンプトファイルの読み込み（ADR-0099 §3）。

プロンプトは `agent_invitro/prompts/<名前>.md` に置き、各モジュールが import 時に読み込む。
プロンプトの変更は prompts/ の差分としてレビュー・記録でき、`prompts_hash()` がリリースの
`prompt_hash`（ADR-0099 §1）になる。

- ファイルの内容をそのまま返す（末尾の改行の有無も含めて文面とみなす）。改行コードだけは LF に
  そろえる（Windows の checkout で CRLF になっても、プロンプトとハッシュが環境で変わらないように）。
- `README.md` は説明用で、プロンプトにもハッシュにも含めない。
- 置き場所は環境変数 `AGENT_PROMPTS_DIR` で上書きできる（既定はパッケージ直上の prompts/）。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_EXCLUDE = {"README.md"}


def prompts_dir() -> Path:
    override = os.environ.get("AGENT_PROMPTS_DIR")
    return Path(override) if override else _DEFAULT_DIR


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def load_prompt(name: str, directory: Path | None = None) -> str:
    """`<directory>/<name>.md` の文面を返す。無ければ FileNotFoundError（起動時に気付けるように）。"""
    return _read((directory or prompts_dir()) / f"{name}.md")


def all_prompts(directory: Path | None = None) -> dict[str, str]:
    """プロンプト名 -> 文面（README.md を除く全 .md）。"""
    directory = directory or prompts_dir()
    return {p.stem: _read(p) for p in sorted(directory.glob("*.md")) if p.name not in _EXCLUDE}


def prompts_hash(directory: Path | None = None) -> str:
    """プロンプト一式の内容ハッシュ（SHA-256 先頭16桁）。ファイル名と文面の両方を含む。"""
    canonical = json.dumps(all_prompts(directory), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
