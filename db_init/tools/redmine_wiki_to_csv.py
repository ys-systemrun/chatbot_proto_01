"""Redmine Wiki の保存ページ（エラー対応）を、シード用 CSV に変換する（1回限りの加工ツール）。

ブラウザの「ページを保存」で保存した Redmine Wiki の HTML（1ページ = 1エラー対応）から、
本文（div.wiki-page）だけを取り出して troubleshooting_article の列名にそろえた CSV を書き出す。
ページ下部の更新者名・添付ファイル一覧などは読まない。

顧客名などの伏せ字は REDACTIONS で置換する（再実行しても同じ結果になるよう、手作業ではなくここに書く）。
出力は UTF-8（BOM なし, LF 改行）で、全フィールドをダブルクォートで囲む。
（BOM を付けると VS Code の Edit csv で先頭の列名に BOM が混ざり、正しく表示されないため付けない。）

使い方（リポジトリルートで実行）:
    python db_init/tools/redmine_wiki_to_csv.py <保存HTMLのディレクトリ> db_init/data/redmine_error_taiou/redmine_error_taiou.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from datetime import datetime
from urllib.parse import unquote

from bs4 import BeautifulSoup, NavigableString, Tag

COLUMNS = ["title", "error_message", "guidance", "cause", "notes", "source_updated_at", "source_page"]

# 伏せ字（置換前, 置換後）。タイトル・本文・エラーメッセージのすべてに適用する。
REDACTIONS = [
    ("（復建技術C）", ""),
    ("静岡県建設コンサルタント様の環境で発生。", "お客様の環境で発生。"),
    ("西日本技術コンサルタント様", ""),
]

# error_message をタイトルではなく本文から取るページ（伏せ字後のタイトル → 本文から抜き出す正規表現）。
# 正規表現の group(1) を、空白・改行を詰めて error_message にする。None はエラーメッセージ無しとする。
ERROR_MESSAGE_FROM_BODY = {
    "Windows10からwindows11にアップデートしたパソコンで維津美が起動しない": r"「(Error 1001[^」]+)」",
    "「マイ単価マスタ」と「マイ歩掛マスタ」のフォルダが開かない": r"「(算術演算の結果オーバーフローが発生しました。)」",
    "「単価マスタ」「歩掛マスタ」を設定する際に「exSQL Server への接続を確立しているときにネットワーク関連またはインスタンス固有のエラーが発生しました。・・・」": r"「(DefaultSource Error:.+?確認してください。\))」",
    "マスタの読み込み時にエラー": r"(Unable to open the physical file.+?使用中です。\)\"\.)",
    "マスタファイルダウンロード・実行時にエラー": r"『(\(Err01\)[^』]+)』",
    "積算ファイルを開く時にマスタの読込中の際「exSQL Serverへの接続を確立している時に～」のエラーが発生する。": r"(connectionstring:.+?確認してください。\))",
    "維津美で積算データの新規作成または、既存の積算データを開く際に「CRCエラー」が発生する。": r"(CRCエラー)",
    "項目配置時に「オブジェクト参照が～」というエラー": r"「(オブジェクト参照がオブジェクトインスタンスに設定されていません。)」",
    "歩掛マスタのEXEファイルを実行しようとすると「InstallCheck.vbs」がメモ帳で開く": None,
}

# 本文中で改行として扱うブロック要素。
BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "pre", "table", "tr", "blockquote"}


def redact(text: str) -> str:
    for before, after in REDACTIONS:
        text = text.replace(before, after)
    return text


def _render(node, out: list[str]) -> None:
    """要素をプレーンテキストに書き出す（<br> と段落は改行、<li> は「・」、<hr> は空行、画像は捨てる）。"""
    if isinstance(node, NavigableString):
        out.append(str(node).replace("\n", ""))
        return
    if not isinstance(node, Tag) or node.name in ("img", "script", "style"):
        return
    if node.name == "a" and "wiki-anchor" in (node.get("class") or []):
        return
    if node.name == "br":
        out.append("\n")
        return
    if node.name == "hr":
        out.append("\n\n")
        return
    if node.name == "li":
        out.append("\n・")
    elif node.name in BLOCK_TAGS:
        out.append("\n")
    for child in node.children:
        _render(child, out)
    if node.name in BLOCK_TAGS:
        out.append("\n")


def to_text(node) -> str:
    out: list[str] = []
    _render(node, out)
    lines = [line.strip().strip("　") for line in "".join(out).split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_error_message(title: str) -> str:
    """タイトル中の「…」のうち最も長いものをエラーメッセージとみなす（無ければ空）。"""
    quoted = [q.strip() for q in re.findall(r"「([^「」]+)」", title)]
    candidates = [q for q in quoted if len(q) >= 8]
    return max(candidates, key=len) if candidates else ""


def error_message_for(title: str, guidance: str) -> str:
    if title not in ERROR_MESSAGE_FROM_BODY:
        return extract_error_message(title)
    pattern = ERROR_MESSAGE_FROM_BODY[title]
    if pattern is None:
        return ""
    m = re.search(pattern, guidance, re.DOTALL)
    if not m:
        raise ValueError(f"error message pattern not found in body: {title}")
    return re.sub(r"\s+", " ", m.group(1)).strip()


def parse_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    wiki = soup.select_one("div.wiki.wiki-page")
    if wiki is None:
        raise ValueError("div.wiki.wiki-page not found")
    h1 = wiki.find("h1")
    title = redact(to_text(h1)) if h1 else ""
    if h1:
        h1.decompose()
    guidance = redact(to_text(wiki)).strip()

    updated_at = ""
    info = soup.select_one("p.wiki-update-info")
    if info:
        for a in info.find_all("a", title=True):
            try:
                updated_at = datetime.strptime(a["title"], "%Y/%m/%d %H:%M").isoformat(sep=" ")
                break
            except ValueError:
                continue

    page = ""
    for a in soup.select("div.contextual a[href$='/edit']"):
        m = re.search(r"/wiki/([^/]+)/edit$", a["href"])
        if m:
            page = unquote(m.group(1))
            break

    return {
        "title": title,
        "error_message": error_message_for(title, guidance),
        "guidance": guidance,
        "cause": "",
        "notes": "",
        "source_updated_at": updated_at,
        "source_page": page,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("src_dir", help="Redmine Wiki を保存した HTML のディレクトリ")
    parser.add_argument("out_csv", help="出力する CSV のパス")
    args = parser.parse_args()

    rows = []
    for path in sorted(glob.glob(os.path.join(args.src_dir, "*.html"))):
        with open(path, encoding="utf-8") as f:
            try:
                row = parse_page(f.read())
            except ValueError as e:
                print(f"skip {os.path.basename(path)}: {e}", file=sys.stderr)
                continue
        if not row["title"] or not row["guidance"]:
            print(f"skip {os.path.basename(path)}: empty title or body", file=sys.stderr)
            continue
        rows.append(row)

    titles = [r["title"] for r in rows]
    duplicated = {t for t in titles if titles.count(t) > 1}
    if duplicated:
        raise SystemExit(f"duplicated titles (must be unique): {sorted(duplicated)}")

    rows.sort(key=lambda r: r["title"])
    os.makedirs(os.path.dirname(os.path.abspath(args.out_csv)), exist_ok=True)
    with open(args.out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
