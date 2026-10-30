"""シード用 CSV を ADR-0108 の書式に書き直す（列の並びと値は変えない。必要なら列名だけ変える）。

書式: UTF-8（BOM なし）・LF 改行・全フィールドをダブルクォートで囲む。
読み込みは BOM の有無・CRLF/LF・引用符の有無を問わない。値（セル内の改行を含む）はそのまま書き戻す。

使い方（リポジトリルートで実行）:
    python db_init/tools/normalize_csv.py db_init/data/hiroba_qa/category.csv
    python db_init/tools/normalize_csv.py db_init/data/redmine_error_taiou/redmine_error_taiou.csv --rename guid=uuid
"""

from __future__ import annotations

import argparse
import csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="書き直す CSV（上書きする）")
    parser.add_argument("--rename", action="append", default=[], metavar="OLD=NEW", help="列名を変える（複数指定可）")
    args = parser.parse_args()
    renames = dict(r.split("=", 1) for r in args.rename)

    with open(args.path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    unknown = set(renames) - set(header)
    if unknown:
        raise SystemExit(f"no such columns: {sorted(unknown)}")
    rows[0] = [renames.get(name, name) for name in header]

    with open(args.path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    print(f"rewrote {len(rows) - 1} rows: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
