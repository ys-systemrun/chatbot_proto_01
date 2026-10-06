"""ゴールデンセット評価（ADR-0099 §5 段階③）の採点・実行・比較を検証する（AWS・Bedrock には触れない）。"""

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from runner import golden, judge, run, scoring

QA_GUID = "11111111-1111-1111-1111-111111111111"


def _repo(tmp_path):
    (tmp_path / "db_init/data/hiroba_qa").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    (tmp_path / "db_init/data/hiroba_qa/exportjson_withguid.json").write_text(json.dumps([
        {"guid": QA_GUID, "title": "見積書の複製", "answer": "［複写］ボタンで複製します。", "question": "q", "category": "c"},
        {"guid": "22222222-2222-2222-2222-222222222222", "title": "別QA", "answer": "別回答", "question": "q", "category": "c"},
    ], ensure_ascii=False), encoding="utf-8")
    (tmp_path / "db_init/data/hiroba_qa/question_altered.csv").write_text(
        f"qa_id,text\n{QA_GUID},見積書を複製したい\n{QA_GUID},見積書のコピー方法\n"
        "22222222-2222-2222-2222-222222222222,別の質問\n", encoding="utf-8")
    (tmp_path / "data/eval_queries.csv").write_text(
        f'query,qa_id\n"見積書を複製するには",{QA_GUID}\n"ContainerNotFound",9c8e1b0c-0000-0000-0000-000000000000\n',
        encoding="utf-8")
    (tmp_path / "data/eval_noise_queries.csv").write_text('query\n"おすすめのカフェは？"\n', encoding="utf-8")
    return tmp_path


def test_build_initial_golden_is_deterministic_and_loadable(tmp_path):
    repo = _repo(tmp_path)
    items = golden.build_initial(repo, sample=2, seed=42)
    assert items == golden.build_initial(repo, sample=2, seed=42)
    assert [i["category"] for i in items] == ["handpicked", "handpicked", "out_of_scope",
                                              "paraphrase_indexed", "paraphrase_indexed"]
    assert items[0]["expected_source_ids"] == f"qa:{QA_GUID}"
    assert items[1]["expected_source_ids"] == "" and "シード元データの QA に無い" in items[1]["note"]

    path = tmp_path / "golden.csv"
    golden.write(path, items)
    loaded = golden.load(path)
    assert loaded[0]["expected_source_ids"] == [f"qa:{QA_GUID}"]
    assert loaded[2]["should_answer"] is False
    ref = golden.reference_answer(loaded[0], golden.load_qa_answers(repo))
    assert "［複写］ボタン" in ref


def test_source_rank_and_decline():
    sources = [{"source_type": "qa", "id": "x"}, {"source_type": "qa", "id": QA_GUID}]
    assert scoring.source_rank([f"qa:{QA_GUID}"], sources) == 2
    assert scoring.source_rank([f"qa:{QA_GUID}"], [{"source_type": "qa", "id": "x"}]) == 0
    assert scoring.source_rank([], sources) is None
    assert scoring.source_rank([f"qa:{QA_GUID}"], None) is None  # 段階③以前の agent（出典なし）

    assert scoring.is_declined("申し訳ございません、ご提供いただいた情報が不足しています。", sources, "pipeline")
    assert scoring.is_declined("どの画面で発生しましたか？", [], "agentic")  # 逆質問
    assert not scoring.is_declined("手順は次のとおりです。", sources, "agentic")


def test_parse_json_object_tolerates_fences_and_preamble():
    assert judge.parse_json_object('{"correctness": 4}') == {"correctness": 4}
    assert judge.parse_json_object('```json\n{"correctness": 4}\n```') == {"correctness": 4}
    assert judge.parse_json_object('採点結果: {"correctness": 3, "reason": "x"}') == {"correctness": 3, "reason": "x"}
    assert judge.parse_json_object("JSONなし") is None


class FakeClient:
    """Anthropic SDK の messages.create を置き換える（応答を順に返す）。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        stop, text = self.replies.pop(0)
        return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def _judge(replies):
    return judge.Judge(model="anthropic.claude-opus-5-5", client=FakeClient(replies))


def test_judge_scores_and_retries_bad_json():
    j = _judge([("end_turn", "うまく書けませんでした"), ("end_turn", '{"correctness": 4, "faithfulness": 5, "reason": "要点を含む"}')])
    result = j.score("Q", True, "模範解答", "参考情報", "回答")
    assert (result["correctness"], result["faithfulness"], result["judge_error"]) == (4, 5, None)
    assert len(j._client.calls) == 2
    call = j._client.calls[0]
    assert call["output_config"] == {"effort": "medium"} and "thinking" not in call
    assert json.loads(call["messages"][0]["content"])["reference_answer"] == "模範解答"


def test_judge_declined_is_combined_with_deterministic_check(tmp_path):
    """出典を返さない agent の逆質問は、決定的な判定では拾えないため LLM の declined で補う。"""
    repo = _repo(tmp_path)
    golden_path = tmp_path / "g.csv"
    golden.write(golden_path, [{"id": "a", "question": "見積書を複製するには", "expected_source_ids": f"qa:{QA_GUID}",
                                "should_answer": "true"}])
    j = _judge([("end_turn", '{"correctness": 1, "faithfulness": null, "declined": true, "reason": "逆質問"}')])
    out = run.run("http://x", golden_path, "agentic", tmp_path / "runs", repo, judge=j,
                  ask=lambda *_a: {"answer": "どの画面ですか？", "sources": None, "context": "", "ask_mode": "agentic",
                                   "release_id": "r", "model": "m", "latency_ms": 1, "error": None},
                  fetch_release=lambda _u: None, log=lambda _m: None)
    rows, _ = run.load_run(out)
    assert rows[0]["declined"] is True and rows[0]["judge_declined"] is True


def test_judge_falls_back_on_refusal_and_ignores_correctness_when_out_of_scope():
    j = _judge([("refusal", ""), ("end_turn", '{"correctness": 5, "faithfulness": null, "reason": "控えた"}')])
    result = j.score("Q", False, None, "", "範疇を超えるため")
    assert result["judge_model"] == judge.FALLBACK_MODEL
    assert result["correctness"] is None  # 範囲外の質問は正しさを採点しない

    j = _judge([("refusal", ""), ("refusal", "")])
    assert "refusal" in j.score("Q", True, None, "", "A")["judge_error"]


def test_run_writes_results_and_compares_with_previous(tmp_path):
    repo = _repo(tmp_path)
    golden_path = tmp_path / "evals/golden/v1.csv"
    golden.write(golden_path, golden.build_initial(repo, sample=1, seed=1))
    runs = tmp_path / "evals/runs"
    times = iter([datetime(2026, 10, 6, 10, 0, 0), datetime(2026, 10, 6, 10, 5, 0),
                  datetime(2026, 10, 6, 11, 0, 0), datetime(2026, 10, 6, 11, 5, 0)])

    def make_ask(good):
        def ask(base_url, mode, question):
            if "カフェ" in question:
                return {"answer": "範疇を超えるため、お答えできません。", "sources": [], "context": "", "ask_mode": mode,
                        "release_id": "r1", "model": "m", "latency_ms": 10, "error": None}
            sources = [{"source_type": "qa", "id": QA_GUID if good else "zzz"}]
            return {"answer": "回答", "sources": sources, "context": "Q: x", "ask_mode": mode,
                    "release_id": "r1", "model": "m", "latency_ms": 10, "error": None}
        return ask

    j = _judge([("end_turn", '{"correctness": 2, "faithfulness": 4, "reason": "不足"}')] * 3
               + [("end_turn", '{"correctness": 5, "faithfulness": 5, "reason": "問題なし"}')] * 3)
    common = dict(base_url="http://x", golden_path=golden_path, mode="agentic", runs_dir=runs, repo=repo,
                  judge=j, fetch_release=lambda _u: {"release_id": "r1", "git_commit": "abc"},
                  now=lambda: next(times), log=lambda _m: None)
    first = run.run(ask=make_ask(False), **common)
    second = run.run(ask=make_ask(True), **common)

    rows, meta = run.load_run(second)
    assert meta["release"]["git_commit"] == "abc" and meta["judge"]["model"] == "anthropic.claude-opus-5-5"
    by_id = {r["id"]: r for r in rows}
    assert by_id["h001"]["source_rank"] == 1 and by_id["h001"]["correctness"] == 5
    assert by_id["n001"]["declined"] is True and by_id["n001"]["correctness"] is None
    assert by_id["h002"]["source_rank"] is None  # 正解出典が無い質問は出典を採点しない

    summary = (second / "summary.md").read_text(encoding="utf-8")
    assert first.name in summary and "改善した質問" in summary

    # history.csv: 1回1行・数値と版のみ（質問・回答の文は入らない）
    import csv as _csv
    history = list(_csv.DictReader((runs.parent / "history.csv").open(encoding="utf-8")))
    assert [h["run_id"] for h in history] == [first.name, second.name]
    assert history[1]["git_commit"] == "abc" and history[1]["source_hit_at_1"] == "1.0"
    text = (runs.parent / "history.csv").read_text(encoding="utf-8")
    assert "見積書" not in text and "回答" not in text
    agg = scoring.aggregate(rows)
    assert agg["source_hit_at_1"] == 1.0 and agg["out_of_scope_decline_rate"] == 1.0


def test_duplicate_golden_ids_are_rejected(tmp_path):
    path = tmp_path / "g.csv"
    golden.write(path, [{"id": "a", "question": "q"}, {"id": "a", "question": "q2"}])
    with pytest.raises(ValueError):
        golden.load(path)
