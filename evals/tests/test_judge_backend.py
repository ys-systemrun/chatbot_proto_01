"""採点バックエンド（ADR-0101）: claude -p の呼び出し方・課金経路の保護・使用量の上限での中断と再開・再採点を検証する。
claude CLI・Bedrock には触れない（subprocess.run を差し替える）。"""

import csv
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from runner import golden, judge, run
from test_run import PRICES, QA_GUID, FakeClient, _repo

GOOD = '{"correctness": 4, "faithfulness": 5, "declined": false, "reason": "要点を含む"}'


def _result(text=GOOD, model="claude-opus-5-5", **extra):
    """claude -p --output-format json の結果（2.1.287 で確かめた形のうち、使う項目だけ）。"""
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": False, "result": text, "total_cost_usd": 0.01,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 0,
                  "cache_read_input_tokens": 0, "output_tokens_details": {"thinking_tokens": 300}},
        "modelUsage": {model: {"inputTokens": 1000, "outputTokens": 500,
                               "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}},
        **extra,
    })


def _api_error(status, text):
    """API の失敗時の形（subtype は success のまま、is_error=true・api_error_status に HTTP ステータス）。"""
    return json.dumps({"type": "result", "subtype": "success", "is_error": True, "api_error_status": status,
                       "result": text, "usage": {"input_tokens": 0, "output_tokens": 0}, "modelUsage": {}})


class FakeCli:
    """subprocess.run の代わり。claude -p の応答を順に返し、呼び出し内容を記録する。"""

    def __init__(self, replies, auth_method="oauth_token"):
        self.replies = list(replies)
        self.auth_method = auth_method
        self.calls = []

    def __call__(self, cmd, input=None, env=None, **kwargs):
        self.calls.append({"cmd": cmd, "input": input, "env": env})
        if cmd[1:] == ["--version"]:
            return SimpleNamespace(stdout="2.1.289 (Claude Code)\n", stderr="", returncode=0)
        if cmd[1:] == ["auth", "status"]:
            return SimpleNamespace(stdout=json.dumps({"loggedIn": True, "authMethod": self.auth_method}),
                                   stderr="", returncode=0)
        reply = self.replies.pop(0)
        return SimpleNamespace(stdout=reply, stderr="", returncode=0 if '"is_error": false' in reply else 1)

    @property
    def judge_calls(self):
        return [c for c in self.calls if "-p" in c["cmd"]]


def _claude_judge(cli, monkeypatch, model=None):
    monkeypatch.setattr(judge, "load_prices", lambda path=judge.PRICES_FILE: PRICES)
    return judge.make_judge("claude-code", model, oauth_token="sk-ant-oat-test", run=cli)


@pytest.fixture(autouse=True)
def _billing_env(monkeypatch):
    """課金経路を変えうる変数がランナーの環境にあっても、claude -p には渡らないことを確かめるために置く。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-should-not-be-used")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("CLAUDE_CODE_EFFORT_LEVEL", "max")


def test_claude_code_call_uses_fixed_flags_and_subscription_only_env(monkeypatch):
    cli = FakeCli([_result()])
    j = _claude_judge(cli, monkeypatch, model="anthropic.claude-opus-5-5")
    result = j.score("Q", True, "模範解答", "参考情報", "回答")

    assert (result["correctness"], result["faithfulness"], result["judge_model"]) == (4, 5, "claude-opus-5-5")
    call = cli.judge_calls[0]
    cmd = call["cmd"]
    assert cmd[:2] == ["claude", "--safe-mode"] and "-p" in cmd
    assert cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--max-turns") + 1] == "1"
    assert cmd[cmd.index("--model") + 1] == "claude-opus-5-5"  # anthropic. 接頭辞は外す
    assert cmd[cmd.index("--effort") + 1] == "medium" and cmd[cmd.index("--output-format") + 1] == "json"
    assert "--no-session-persistence" in cmd and "--json-schema" not in cmd and "--bare" not in cmd
    with open(cmd[cmd.index("--system-prompt-file") + 1], encoding="utf-8", newline="") as f:
        assert f.read() == j.prompt and "\r\n" not in j.prompt  # prompt_hash と同じ内容（LF）を渡す
    assert json.loads(call["input"])["reference_answer"] == "模範解答"  # 入力は標準入力で渡す

    env = call["env"]
    for key in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_USE_BEDROCK", "AWS_SECRET_ACCESS_KEY", "CLAUDE_CODE_EFFORT_LEVEL"):
        assert key not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat-test" and env["DISABLE_AUTOUPDATER"] == "1"

    # トークン数は modelUsage から取り、Opus 5.5 の単価で API 単価換算する
    assert (result["judge_calls"], result["judge_input_tokens"], result["judge_output_tokens"]) == (1, 1000, 500)
    assert result["judge_thinking_tokens"] == 300 and result["judge_cost_usd"] == 0.014
    assert j.meta()["backend"] == "claude-code" and j.meta()["cli_version"] == "2.1.289 (Claude Code)"


def test_claude_code_counts_one_call_even_when_several_models_report_usage(monkeypatch):
    reply = json.loads(_result())
    reply["modelUsage"]["claude-haiku-4-5"] = {"inputTokens": 10, "outputTokens": 5}
    j = _claude_judge(FakeCli([json.dumps(reply)]), monkeypatch)
    result = j.score("Q", True, None, "", "A")
    assert result["judge_calls"] == 1 and result["judge_input_tokens"] == 1010
    assert result["judge_cost_usd"] is None  # 単価表に無いモデルを含むので費用は出さない


def test_preflight_rejects_api_key_auth(monkeypatch):
    with pytest.raises(judge.JudgeSetupError, match="サブスクリプション"):
        _claude_judge(FakeCli([], auth_method="api_key"), monkeypatch)


def test_preflight_reports_missing_cli(monkeypatch):
    def missing(*_a, **_k):
        raise FileNotFoundError("claude")
    with pytest.raises(judge.JudgeSetupError, match="見つかりません"):
        _claude_judge(missing, monkeypatch)


def test_claude_code_refusal_falls_back_to_opus_4_8(monkeypatch):
    cli = FakeCli([_result("", stop_reason="refusal"), _result(GOOD, model="claude-opus-4-8")])
    result = _claude_judge(cli, monkeypatch).score("Q", True, None, "", "A")
    assert result["judge_model"] == "claude-opus-4-8" and result["judge_calls"] == 2
    second = cli.judge_calls[1]["cmd"]
    assert second[second.index("--model") + 1] == "claude-opus-4-8"


def test_usage_limit_and_auth_failure_abort_but_other_errors_are_recorded(monkeypatch):
    for reply in (_api_error(None, "You've hit your session limit · resets 3:45pm"), _api_error(429, "Rate limited")):
        with pytest.raises(judge.UsageLimitError):
            _claude_judge(FakeCli([reply]), monkeypatch).score("Q", True, None, "", "A")
    # claude auth status はトークンの有効性を確かめないため、無効なトークンは最初の呼び出しの 401 で分かる
    invalid = _api_error(401, "Failed to authenticate. API Error: 401 OAuth access token is invalid.")
    with pytest.raises(judge.JudgeAuthError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        _claude_judge(FakeCli([invalid]), monkeypatch).score("Q", True, None, "", "A")

    other = _api_error(500, "boom")
    result = _claude_judge(FakeCli([other, other]), monkeypatch).score("Q", True, None, "", "A")
    assert "boom" in result["judge_error"] and result["judge_calls"] == 0


def _golden(tmp_path, repo):
    path = tmp_path / "evals/golden/v2.csv"
    golden.write(path, [
        {"id": "a", "question": "見積書を複製するには", "expected_source_ids": f"qa:{QA_GUID}", "should_answer": "true"},
        {"id": "b", "question": "見積書のコピー方法", "expected_source_ids": f"qa:{QA_GUID}", "should_answer": "true"},
        {"id": "c", "question": "おすすめのカフェは？", "should_answer": "false"},
    ])
    return path


def _ask(base_url, mode, question):
    if "カフェ" in question:
        return {"answer": "範疇を超えるため、お答えできません。", "sources": [], "context": "", "ask_mode": mode,
                "release_id": "r1", "model": "m", "latency_ms": 10, "error": None}
    return {"answer": "［複写］ボタンで複製します。", "sources": [{"source_type": "qa", "id": QA_GUID}],
            "context": "Q: 見積書の複製\nA: ［複写］ボタン", "ask_mode": mode,
            "release_id": "r1", "model": "m", "latency_ms": 10, "error": None}


def test_usage_limit_stops_judging_and_only_missing_resumes(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    golden_path = _golden(tmp_path, repo)
    runs = tmp_path / "evals/runs"
    history = tmp_path / "evals/history.csv"
    limit = _api_error(None, "You've hit your weekly limit · resets Mon 12:00am")
    cli = FakeCli([_result(), limit])
    logs = []
    out = run.run("http://x", golden_path, "agentic", runs, repo, judge=_claude_judge(cli, monkeypatch),
                  ask=_ask, fetch_release=lambda _u: None, now=lambda: datetime(2026, 10, 14, 10, 0, 0),
                  log=logs.append, history_path=history)

    rows, meta = run.load_run(out)
    assert [r["judge_calls"] for r in rows] == [1, None, None]  # 上限以降は「採点不可」で埋めない
    assert rows[0]["context"].startswith("Q: 見積書の複製")  # 回答時の参考情報を保存する
    assert meta["judge_incomplete"]["unjudged"] == 2 and meta["judge"]["backend"] == "claude-code"
    assert "採点が途中で止まりました" in (out / "summary.md").read_text(encoding="utf-8")
    assert any("使用量の上限" in m for m in logs)

    resumed = run.rejudge(out, _claude_judge(FakeCli([_result(), _result()]), monkeypatch), runs, repo,
                          only_missing=True, log=lambda _m: None, history_path=history)
    assert resumed == out
    rows, meta = run.load_run(out)
    assert [r["judge_calls"] for r in rows] == [1, 1, 1] and meta["judge_incomplete"] is None
    assert rows[2]["declined"] is True and rows[2]["correctness"] is None
    lines = list(csv.DictReader(history.open(encoding="utf-8")))
    assert [h["run_id"] for h in lines] == [out.name]  # 同じ実行の行を置き換える（重複させない）
    assert lines[0]["judge_backend"] == "claude-code" and lines[0]["judge_calls"] == "3"


def test_full_rejudge_with_other_backend_creates_new_run(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    golden_path = _golden(tmp_path, repo)
    runs = tmp_path / "evals/runs"
    history = tmp_path / "evals/history.csv"
    src = run.run("http://x", golden_path, "agentic", runs, repo, judge=None, ask=_ask,
                  fetch_release=lambda _u: None, now=lambda: datetime(2026, 10, 14, 10, 0, 0),
                  log=lambda _m: None, history_path=history)

    bedrock = judge.Judge(model="anthropic.claude-opus-5-5", client=FakeClient([("end_turn", GOOD)] * 3),
                          prices=PRICES)
    out = run.rejudge(src, bedrock, runs, repo, now=lambda: datetime(2026, 10, 14, 11, 0, 0),
                      log=lambda _m: None, history_path=history)
    assert out != src and (src / "results.jsonl").exists()
    rows, meta = run.load_run(out)
    assert meta["answers_from"] == src.name and meta["judge"]["backend"] == "bedrock"
    assert [r["judge_calls"] for r in rows] == [1, 1, 1]
    assert "の回答を採点し直したもの" in (out / "summary.md").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="採点条件"):
        run.rejudge(out, _claude_judge(FakeCli([]), monkeypatch), runs, repo, only_missing=True,
                    log=lambda _m: None, history_path=history)


def test_rejudge_rejects_runs_without_context(tmp_path):
    repo = _repo(tmp_path)
    golden_path = _golden(tmp_path, repo)
    runs = tmp_path / "evals/runs"
    src = run.run("http://x", golden_path, "agentic", runs, repo, judge=None, ask=_ask,
                  fetch_release=lambda _u: None, now=lambda: datetime(2026, 10, 14, 10, 0, 0),
                  log=lambda _m: None, history_path=tmp_path / "h.csv")
    rows, meta = run.load_run(src)
    for row in rows:
        row.pop("context")
    (src / "results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                                       encoding="utf-8")
    with pytest.raises(ValueError, match="context"):
        run.rejudge(src, None, runs, repo, log=lambda _m: None)


def test_previous_run_without_backend_is_treated_as_bedrock(tmp_path):
    old = {"judge": {"model": "anthropic.claude-opus-5-5", "prompt_hash": "p"}}
    new_bedrock = {"judge": {"model": "anthropic.claude-opus-5-5", "prompt_hash": "p", "backend": "bedrock"}}
    new_cc = {"judge": {"model": "anthropic.claude-opus-5-5", "prompt_hash": "p", "backend": "claude-code",
                        "cli_version": "2.1.289"}}
    assert run.judge_key(old) == run.judge_key(new_bedrock)
    assert run.judge_key(old) != run.judge_key(new_cc)
    assert run.judge_key({**new_cc, "judge": {**new_cc["judge"], "cli_version": "2.2.0"}}) == run.judge_key(new_cc)
