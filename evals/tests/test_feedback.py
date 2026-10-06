"""pull-feedback（ADR-0099 §5）の変換と増分取り込みを検証する。"""

import json
from datetime import datetime

from runner import feedback

CONVS = [
    {
        "id": "c1",
        "created_at": "2026-10-06T10:00:00+09:00",
        "messages": [
            {"order": 1, "role": 1, "content": "参考情報:\nQ: x\nA: y\n\n質問:\n見積書を複製したい", "evaluation": None},
            {"order": 2, "role": 2, "content": "回答1", "evaluation": 2, "model": "m",
             "ask_mode": "agentic", "release_id": "r1", "release": {"release_id": "r1", "git_commit": "abc"},
             "evaluation_comment": "手順が古い", "evaluated_at": "2026-10-06T10:05:00+09:00",
             "created_at": "2026-10-06T10:01:00+09:00"},
            {"order": 3, "role": 1, "content": "参考情報:\n\n\n質問:\nありがとう", "evaluation": None},
            {"order": 4, "role": 2, "content": "どういたしまして", "evaluation": 0},  # 未評価は対象外
        ],
    },
    {
        "id": "c2",
        "created_at": "2026-10-06T11:00:00+09:00",
        "messages": [
            {"order": 1, "role": 1, "content": "素の質問", "evaluation": None},
            {"order": 2, "role": 2, "content": "回答2", "evaluation": 1, "evaluated_at": None},
        ],
    },
]


def test_split_user_content():
    assert feedback.split_user_content("参考情報:\nQ: x\n\n質問:\n本文") == ("本文", "Q: x")
    assert feedback.split_user_content("素の質問") == ("素の質問", None)
    assert feedback.split_user_content(None) == ("", None)


def test_flatten_pairs_question_and_answer():
    rows = feedback.flatten(CONVS)

    assert [(r["conversation_id"], r["order"], r["evaluation"]) for r in rows] == [
        ("c1", 2, "bad"),
        ("c2", 2, "good"),
    ]
    bad = rows[0]
    assert bad["question"] == "見積書を複製したい"
    assert bad["context"] == "Q: x\nA: y"
    assert bad["evaluation_comment"] == "手順が古い"
    assert bad["release"]["git_commit"] == "abc"
    assert rows[1]["question"] == "素の質問" and rows[1]["context"] is None


def test_pull_writes_only_new_rows(tmp_path):
    convs = json.loads(json.dumps(CONVS))
    fetch = lambda _url: convs  # noqa: E731

    first = feedback.pull("http://x", tmp_path, now=datetime(2026, 10, 6, 12, 0, 0), fetch=fetch)
    assert first.name == "20261006-120000.jsonl"
    assert len(first.read_text(encoding="utf-8").splitlines()) == 2

    # 変化なし → 書かない
    assert feedback.pull("http://x", tmp_path, now=datetime(2026, 10, 6, 13, 0, 0), fetch=fetch) is None

    # 理由を付け直した1件だけが増分になる
    convs[0]["messages"][1]["evaluation_comment"] = "出典は正しいが手順が古い"
    convs[0]["messages"][1]["evaluated_at"] = "2026-10-06T12:30:00+09:00"
    second = feedback.pull("http://x", tmp_path, now=datetime(2026, 10, 6, 14, 0, 0), fetch=fetch)
    lines = second.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["evaluation_comment"] == "出典は正しいが手順が古い"
    assert "👎 1" in feedback.summarize(second)
