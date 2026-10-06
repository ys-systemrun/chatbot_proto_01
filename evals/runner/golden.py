"""ゴールデンセット（ADR-0099 §5）の読み込みと初版の作成。

ゴールデンセットは `evals/golden/<名前>.csv`（git 管理）。列:

| 列 | 内容 |
|---|---|
| id | 質問の ID（実行結果どうしの比較キー。変更しない） |
| question | 質問文 |
| expected_source_ids | 正解の出典（`qa:<guid>` / `troubleshooting:<id>`。空白区切りで複数可。空なら出典は採点しない） |
| expected_answer_points | 回答に含むべき要点（任意。空なら正解出典の回答文を模範解答として採点に使う） |
| category | 分類（handpicked / paraphrase_indexed / out_of_scope / feedback など） |
| should_answer | `true`=回答すべき / `false`=範囲外で回答を控えるのが正解 |
| note | 補足 |

QA の回答文はゴールデンセットに複製しない。採点時に DVC 管理のシード元データ
（`db_init/data/hiroba_qa/exportjson_withguid.json`）から引く（ADR-0097 のデータを git に入れない方針）。
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path

COLUMNS = [
    "id",
    "question",
    "expected_source_ids",
    "expected_answer_points",
    "category",
    "should_answer",
    "note",
]

QA_JSON = Path("db_init/data/hiroba_qa/exportjson_withguid.json")
PARAPHRASE_CSV = Path("db_init/data/hiroba_qa/question_altered.csv")
HANDPICKED_CSV = Path("data/eval_queries.csv")
NOISE_CSV = Path("data/eval_noise_queries.csv")


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    items = []
    seen = set()
    for row in rows:
        if row["id"] in seen:
            raise ValueError(f"{path}: id が重複しています: {row['id']}")
        seen.add(row["id"])
        items.append({
            "id": row["id"],
            "question": row["question"],
            "expected_source_ids": (row.get("expected_source_ids") or "").split(),
            "expected_answer_points": row.get("expected_answer_points") or "",
            "category": row.get("category") or "",
            "should_answer": (row.get("should_answer") or "true").strip().lower() != "false",
            "note": row.get("note") or "",
        })
    return items


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_qa_answers(repo: Path) -> dict[str, dict] | None:
    """guid -> {"title", "answer"}。シード元データが無い（dvc pull 前）なら None。"""
    path = repo / QA_JSON
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return {d["guid"]: {"title": d.get("title"), "answer": d.get("answer")} for d in data}


def reference_answer(item: dict, qa_answers: dict[str, dict] | None) -> str | None:
    """採点に使う模範解答。要点があればそれを優先し、無ければ正解 QA の回答文を使う。"""
    if item["expected_answer_points"]:
        return item["expected_answer_points"]
    if not qa_answers:
        return None
    texts = []
    for sid in item["expected_source_ids"]:
        source_type, _, source_id = sid.partition(":")
        if source_type == "qa" and source_id in qa_answers:
            qa = qa_answers[source_id]
            texts.append(f"Q: {qa['title']}\nA: {qa['answer']}")
    return "\n\n".join(texts) or None


def build_initial(repo: Path, sample: int, seed: int) -> list[dict]:
    """初版のゴールデンセットを作る。

    - handpicked: data/eval_queries.csv（手作りの質問と正解 QA）
    - out_of_scope: data/eval_noise_queries.csv（範囲外。回答を控えるのが正解）
    - paraphrase_indexed: 言い換え質問文から seed 固定で抽出（1 QA につき1問）。言い換え質問文は検索用に
      埋め込み済みのため、出典の正しさは楽観的に出る（回答の質の比較には使える）
    """
    qa_answers = load_qa_answers(repo)
    if qa_answers is None:
        raise FileNotFoundError(f"{repo / QA_JSON} がありません。先に terraform\\dvc.bat pull を実行してください。")

    items: list[dict] = []
    with (repo / HANDPICKED_CSV).open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            known = row["qa_id"] in qa_answers
            items.append({
                "id": f"h{i:03d}",
                "question": row["query"],
                "expected_source_ids": f"qa:{row['qa_id']}" if known else "",
                "expected_answer_points": "",
                "category": "handpicked",
                "should_answer": "true",
                "note": "" if known else f"正解 ID {row['qa_id']} はシード元データの QA に無い（出典は採点しない。要点の記入を推奨）",
            })
    with (repo / NOISE_CSV).open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            items.append({
                "id": f"n{i:03d}",
                "question": row["query"],
                "expected_source_ids": "",
                "expected_answer_points": "",
                "category": "out_of_scope",
                "should_answer": "false",
                "note": "",
            })

    by_qa: dict[str, list[str]] = {}
    with (repo / PARAPHRASE_CSV).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["qa_id"] in qa_answers:
                by_qa.setdefault(row["qa_id"], []).append(row["text"])
    rng = random.Random(seed)
    for i, qa_id in enumerate(rng.sample(sorted(by_qa), min(sample, len(by_qa))), start=1):
        items.append({
            "id": f"p{i:03d}",
            "question": rng.choice(sorted(by_qa[qa_id])),
            "expected_source_ids": f"qa:{qa_id}",
            "expected_answer_points": "",
            "category": "paraphrase_indexed",
            "should_answer": "true",
            "note": "",
        })
    return items


def write(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for item in items:
            writer.writerow({k: item.get(k, "") for k in COLUMNS})
