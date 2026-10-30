"""トラブルシューティング記事の HTML を、シード用 CSV に変換する（1回限りの加工ツール, ADR-0108）。

これまでシードが行っていた HTML の解析（troubleshooting_import.parse_articles, ADR-0076）をそのまま使い、
解析結果を troubleshooting_article の列名にそろえた CSV に書き出す。1 つの HTML から 1 つの CSV を作る
（source_key はシードの TROUBLESHOOTING_SOURCES でファイルごとに決める）。

- uuid は現在の導出値（(source_key, title) から UUID v5, ADR-0106）をそのまま書き出す。検索結果の出典 ID
  （ADR-0107）とゴールデンセットの正解を変えないため。
- body_html（元の表を含む HTML ブロック）も列として書き出す。guidance から作り直すと表の情報が落ちるため。
- 日時は YYYY-MM-DD HH:MM:SS。

出力は ADR-0108 の書式（UTF-8・BOM なし・LF・全フィールドをダブルクォート）。

使い方（リポジトリルートで実行）:
    python db_init/tools/troubleshooting_html_to_csv.py db_init/data/troubleshooting/trouble_shooting.html \
        trouble_shooting db_init/data/troubleshooting/trouble_shooting.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import troubleshooting_import as ti  # noqa: E402

COLUMNS = ["uuid"] + [c for c in ti.ARTICLE_COLUMNS if c not in ("source_key", "uuid")]


def to_row(article: ti.TroubleshootingArticle) -> dict:
    row = {}
    for col in COLUMNS:
        value = getattr(article, col)
        if value is None:
            row[col] = ""
        elif col == "source_updated_at":
            row[col] = value.strftime("%Y-%m-%d %H:%M:%S")
        else:
            row[col] = value
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("html_path", help="トラブルシューティング記事の HTML")
    parser.add_argument("source_key", help="記事の出自（trouble_shooting / trouble_shooting_netauth）。uuid の導出に使う")
    parser.add_argument("out_csv", help="出力する CSV のパス")
    args = parser.parse_args()

    with open(args.html_path, encoding="utf-8") as f:
        articles = ti.parse_articles(f.read(), args.source_key)
    for a in articles:
        for w in a.warnings:
            print(f"WARNING {a.title}: {w}", file=sys.stderr)
    titles = [a.title for a in articles]
    if len(set(titles)) != len(titles):
        raise SystemExit("duplicated titles (must be unique)")

    with open(args.out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        writer.writerows(to_row(a) for a in articles)
    print(f"wrote {len(articles)} rows to {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
