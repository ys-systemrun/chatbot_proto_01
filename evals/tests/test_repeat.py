"""繰り返し実行と揺れを考慮した比較（runner/repeat.py）を検証する（AWS・Bedrock には触れない）。"""

import csv
import json
from datetime import datetime

from runner import golden, repeat, run
from tests.test_run import write_qa_csv

QA = "11111111-1111-1111-1111-111111111111"


def _row(qid, correctness=None, declined=False, should_answer=True, rank=1, error=None):
    return {"id": qid, "question": f"質問{qid}", "should_answer": should_answer, "declined": declined,
            "correctness": correctness, "faithfulness": None, "source_rank": rank, "latency_ms": 10, "error": error}


def test_stats_and_noise_threshold():
    s = repeat.stats([3.0, 3.2, 3.4])
    assert s["mean"] == 3.2 and s["n"] == 3 and s["min"] == 3.0 and s["max"] == 3.4
    assert abs(s["sd"] - 0.2) < 1e-9
    assert repeat.stats([2.0])["sd"] is None
    assert repeat.stats([None]) is None

    a, b = repeat.stats([3.0, 3.2, 3.4]), repeat.stats([3.5, 3.7, 3.9])
    # 2 * sqrt(0.2²/3 + 0.2²/3) ≈ 0.327
    assert repeat.noise_threshold(a, b) == 0.327
    # 片側が1回だけなら、もう片側のばらつきで代用する
    assert repeat.noise_threshold(repeat.stats([3.0]), a) == round(2 * (0.2 ** 2 / 1 + 0.2 ** 2 / 3) ** 0.5, 3)
    assert repeat.noise_threshold(repeat.stats([3.0]), repeat.stats([3.5])) is None


def test_question_value():
    assert repeat.question_value(_row("a", correctness=4)) == 4.0
    assert repeat.question_value(_row("a", correctness=5, declined=True)) == 1.0  # 控えたら 1
    assert repeat.question_value(_row("a", rank=1)) == 5.0                       # 未採点は出典の順位から
    assert repeat.question_value(_row("a", rank=0)) == 1.0
    assert repeat.question_value(_row("n", should_answer=False, declined=True)) == 5.0
    assert repeat.question_value(_row("n", should_answer=False, declined=False)) == 1.0
    assert repeat.question_value(_row("a", error="HTTP 504")) is None


def test_compare_questions_requires_consistent_change():
    before = [[_row("a", 2), _row("b", 3), _row("c", 4)], [_row("a", 3), _row("b", 5), _row("c", 4)]]
    after = [[_row("a", 4), _row("b", 4), _row("c", 4)], [_row("a", 5), _row("b", 2), _row("c", 4)]]
    q = repeat.compare_questions(before, after)
    assert [x[0] for x in q["better"]] == ["a"]    # 2,3 → 4,5: 全回が上回る
    assert [x[0] for x in q["unclear"]] == ["b"]   # 3,5 → 4,2: 重なる
    assert [x[0] for x in q["same"]] == ["c"]


def test_compare_markdown_flags_only_differences_beyond_noise():
    def runs(values):
        return [[_row(f"q{i}", v) for i, v in enumerate(trial)] for trial in values]

    noisy_same = repeat.compare_markdown("A", runs([[3, 3, 3], [4, 3, 3], [3, 3, 4]]),
                                         "B", runs([[3, 4, 3], [3, 3, 3], [4, 3, 3]]))
    assert "揺れの範囲内" in noisy_same and "**改善**" not in noisy_same

    improved = repeat.compare_markdown("A", runs([[2, 2, 2], [2, 3, 2], [2, 2, 3]]),
                                       "B", runs([[5, 5, 5], [5, 4, 5], [5, 5, 4]]))
    assert "**改善**" in improved and "改善した質問" in improved

    single = repeat.compare_markdown("A", runs([[3, 3, 3]]), "B", runs([[4, 4, 4]]))
    assert "1回ずつのため" in single and "判定不可" in single


def _setup(tmp_path):
    (tmp_path / "db_init/data/hiroba_qa").mkdir(parents=True)
    write_qa_csv(tmp_path / "db_init/data/hiroba_qa/hiroba_qa_original.csv", [(QA, "t", "a")])
    golden_path = tmp_path / "evals/golden/v9.csv"
    golden.write(golden_path, [
        {"id": "h001", "question": "見積書を複製するには", "expected_source_ids": f"qa:{QA}", "should_answer": "true"},
        {"id": "n001", "question": "おすすめのカフェは？", "should_answer": "false"},
    ])
    return golden_path


def _ask(hit):
    def ask(base_url, mode, question):
        if "カフェ" in question:
            return {"answer": "範疇を超えるため、お答えできません。", "sources": [], "context": "", "ask_mode": mode,
                    "release_id": "r1", "model": "m", "latency_ms": 10, "error": None}
        return {"answer": "回答", "sources": [{"source_type": "qa", "id": QA if hit else "x"}], "context": "Q: x",
                "ask_mode": mode, "release_id": "r1", "model": "m", "latency_ms": 10, "error": None}
    return ask


def test_repeated_runs_form_a_group(tmp_path):
    golden_path = _setup(tmp_path)
    runs_dir = tmp_path / "evals/runs"
    times = iter([datetime(2026, 10, 16, 10, 0, s) for s in range(0, 60, 1)])
    gid = repeat.group_id(datetime(2026, 10, 16, 9, 0, 0), "v9", "pipeline", 3)
    for i, hit in enumerate([True, False, True], start=1):
        run.run("http://x", golden_path, "pipeline", runs_dir, tmp_path, ask=_ask(hit),
                fetch_release=lambda _u: {"release_id": "r1"}, now=lambda: next(times), log=lambda _m: None,
                repeat={"group": gid, "index": i, "of": 3})

    dirs = repeat.find_group(runs_dir, gid)
    assert [d.name[-3:] for d in dirs] == ["_r1", "_r2", "_r3"]

    # 各回の「前回比較」は同じグループの他の回を相手にしない
    for d in dirs:
        assert "同じ条件の前回実行が無いため" in (d / "summary.md").read_text(encoding="utf-8")

    out = repeat.write_group_summary(runs_dir, gid, run.load_run)
    text = out.read_text(encoding="utf-8")
    assert out.parent.name == "groups" and "3 回" in text
    assert "出典 1位一致率 | 0.667 ± 0.577（0.0〜1.0）" in text   # 1, 0, 1
    assert "h001" in text  # 回ごとに結果が変わった質問（5,1,5）

    history = list(csv.DictReader((tmp_path / "evals/history.csv").open(encoding="utf-8")))
    assert [h["repeat_index"] for h in history] == ["1", "2", "3"] and {h["repeat_group"] for h in history} == {gid}

    name, resolved = repeat.resolve(runs_dir, gid)
    assert name == gid and resolved == dirs
    assert repeat.resolve(runs_dir, dirs[0].name)[1] == [dirs[0]]
    assert repeat.resolve(runs_dir, "no-such")[1] == []
