"""DVC 管理の CSV を、2 つの版のあいだで行・セル単位に比べて HTML で開く（daff を使う）。

DVC のデータ本体は git の管理外のため、git の diff ドライバでは中身を比べられない。
このスクリプトは git から各版の .dvc ファイルを読み、ローカルの DVC キャッシュ（.dvc/cache）から
その版の CSV を取り出して比べる。S3 にも DVC コンテナにも触らない（キャッシュに無い版はエラー）。

使い方（リポジトリルートで実行。daff は `py -m pip install daff` で入れる）:
    # 作業ツリーの編集内容を、最後にコミットした版と比べる
    py db_init/tools/dvc_csv_diff.py db_init/data/knowledge/tag.csv
    # 2 つの版を比べる（ディレクトリを指定すると、変わった CSV をまとめて比べる）
    py db_init/tools/dvc_csv_diff.py db_init/data/knowledge --old 7df5738 --new c8d8f59
    # 主キーの列を指定する（省略時は daff が行の対応を推定する）
    py db_init/tools/dvc_csv_diff.py db_init/data/knowledge/tag.csv --key id

キャッシュに無い版を比べるときは、先に取り寄せておく:
    terraform\\dvc.bat fetch --all-commits db_init/data/knowledge.dvc
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path, PurePosixPath

try:
    import daff
except ImportError:
    raise SystemExit("daff が見つかりません。`py -m pip install daff` で入れてください。")

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / ".dvc" / "cache" / "files" / "md5"
WORKTREE = "worktree"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, encoding="utf-8"
    ).stdout


def git_file(rev: str, path: PurePosixPath) -> str | None:
    """rev 時点のファイルの中身。無ければ None。"""
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"], cwd=REPO, capture_output=True, encoding="utf-8"
    )
    return result.stdout if result.returncode == 0 else None


def find_dvc_file(target: PurePosixPath, rev: str) -> tuple[PurePosixPath, PurePosixPath]:
    """target を含む出力の .dvc ファイルと、その出力のパスを返す（target 自身から親へたどる）。"""
    for out in [target, *target.parents]:
        if str(out) == ".":
            break
        dvc_file = out.with_name(out.name + ".dvc")
        exists = (REPO / dvc_file).exists() if rev == WORKTREE else git_file(rev, dvc_file) is not None
        if exists:
            return dvc_file, out
    raise SystemExit(f"{target} を含む .dvc ファイルが見つかりません（版: {rev}）")


def cache_path(md5: str) -> Path:
    return CACHE / md5[:2] / md5[2:]


def read_cache(md5: str, what: str) -> bytes:
    path = cache_path(md5)
    if not path.exists():
        raise SystemExit(
            f"{what} が DVC キャッシュにありません（{md5}）。\n"
            "先に取り寄せてください: terraform\\dvc.bat fetch --all-commits <対象の .dvc>"
        )
    return path.read_bytes()


def files_at(target: PurePosixPath, rev: str) -> dict[PurePosixPath, bytes | Path]:
    """rev 時点で target 配下にあるファイル（リポジトリからの相対パス → 中身 or 作業ツリーのパス）。"""
    if rev == WORKTREE:
        root = REPO / target
        if root.is_file():
            return {target: root}
        return {
            target / PurePosixPath(p.relative_to(root).as_posix()): p
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    dvc_file, out = find_dvc_file(target, rev)
    text = git_file(rev, dvc_file) or ""
    match = re.search(r"md5:\s*([0-9a-f]{32})(\.dir)?", text)
    if not match:
        raise SystemExit(f"{dvc_file}（版: {rev}）から md5 を読めません")
    md5, is_dir = match.group(1), bool(match.group(2))
    if not is_dir:
        return {out: read_cache(md5, f"{out}（版: {rev}）")} if out == target else {}

    entries = json.loads(read_cache(md5 + ".dir", f"{out} の一覧（版: {rev}）"))
    files: dict[PurePosixPath, bytes | Path] = {}
    for entry in entries:
        path = out / PurePosixPath(entry["relpath"])
        if path == target or target in path.parents:
            files[path] = read_cache(entry["md5"], f"{path}（版: {rev}）")
    return files


def read_bytes(content: bytes | Path) -> bytes:
    return content.read_bytes() if isinstance(content, Path) else content


def read_rows(content: bytes | Path | None) -> list[list[str]]:
    if content is None:
        return []
    # 読み込みは BOM・改行コード・引用符の有無を問わない（ADR-0108 の 10）
    return list(csv.reader(io.StringIO(read_bytes(content).decode("utf-8-sig"), newline="")))


def diff_html(old_rows: list[list[str]], new_rows: list[list[str]], keys: list[str]) -> tuple[str, bool]:
    """daff の差分表（HTML）と、差分があるかどうか。"""
    old_table = daff.PythonTableView(old_rows)
    new_table = daff.PythonTableView(new_rows)
    flags = daff.CompareFlags()
    for key in keys:
        flags.addPrimaryKey(key)
    align = daff.Coopy.compareTables(old_table, new_table, flags).align()
    out_rows: list[list[str]] = []
    out_table = daff.PythonTableView(out_rows)
    highlighter = daff.TableDiff(align, flags)
    highlighter.hilite(out_table)
    render = daff.DiffRender()
    render.render(out_table)
    return render.html(), highlighter.hasDifference()


PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>CSV 差分</title>
<style>
body {{ font-family: sans-serif; margin: 16px; }}
h2 {{ margin-top: 2em; font-size: 1.1em; }}
.note {{ color: #555; }}
table {{ border-collapse: collapse; font-size: 13px; }}
td, th {{ border: 1px solid #ccc; padding: 2px 6px; vertical-align: top; white-space: pre-wrap; max-width: 40em; }}
.add {{ background: #7fff7f; }}
.remove {{ background: #ff7f7f; }}
.modify {{ background: #7f7fff; }}
.conflict {{ background: #f00; }}
.spec {{ background: #aaa; }}
.move {{ background: #ffa; }}
.null {{ color: #888; }}
table tr:first-child td {{ border-top: 1px solid #2D4068; }}
table td:first-child {{ border-left: 1px solid #2D4068; }}
</style></head><body>
<h1>CSV 差分</h1>
<p class="note">旧: {old} ／ 新: {new}。<code>+++</code> 追加行・<code>---</code> 削除行・<code>-&gt;</code> 変更セル（旧-&gt;新）・<code>...</code> 省略した変わらない行。</p>
{body}
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", help="比べる CSV か、そのディレクトリ（リポジトリルートからの相対パス）")
    parser.add_argument("--old", default="HEAD", help="旧の版（git のリビジョン。既定: HEAD）")
    parser.add_argument("--new", default=WORKTREE, help=f"新の版（既定: {WORKTREE} = 作業ツリー）")
    parser.add_argument("--key", action="append", default=[], metavar="COLUMN", help="主キーの列（複数指定可）")
    parser.add_argument("--output", help="HTML の書き出し先（既定: 一時ファイル）")
    parser.add_argument("--no-open", action="store_true", help="ブラウザで開かない")
    args = parser.parse_args()

    target = PurePosixPath(Path(args.target).as_posix().rstrip("/"))
    old_files = files_at(target, args.old)
    new_files = files_at(target, args.new)

    sections: list[str] = []
    for path in sorted(set(old_files) | set(new_files)):
        old, new = old_files.get(path), new_files.get(path)
        if old is not None and new is not None and read_bytes(old) == read_bytes(new):
            continue
        status = "追加" if old is None else "削除" if new is None else "変更"
        print(f"{status}: {path}")
        title = f"<h2>{html.escape(str(path))}（{status}）</h2>"
        if path.suffix.lower() != ".csv":
            sections.append(title + '<p class="note">CSV ではないため、表の差分は出しません。</p>')
            continue
        table, changed = diff_html(read_rows(old), read_rows(new), args.key)
        if not changed:
            table = '<p class="note">値の違いはありません（書式・改行コード・引用符だけの違い）。</p>' + table
        sections.append(title + table)

    if not sections:
        print(f"差分はありません: {target}（{args.old} → {args.new}）")
        return 0

    page = PAGE.format(old=html.escape(args.old), new=html.escape(args.new), body="\n".join(sections))
    if args.output:
        output = Path(args.output)
    else:
        fd, name = tempfile.mkstemp(prefix="dvc_csv_diff_", suffix=".html")
        os.close(fd)
        output = Path(name)
    output.write_text(page, encoding="utf-8")
    print(f"HTML: {output}")
    if not args.no_open:
        webbrowser.open(output.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
