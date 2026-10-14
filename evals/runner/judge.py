"""LLM 採点（ADR-0099 §5）。Claude Opus で回答を採点する。

- 採点モデルは回答用モデル（Amazon Nova）とは別。既定は Claude Opus 5.5（`EVAL_JUDGE_MODEL_ID` で変更可）。
- 採点の実行方法（バックエンド）は `bedrock`（既定）と `claude-code` から選ぶ（ADR-0101）。
  - `bedrock`: Amazon Bedrock を Anthropic SDK の Bedrock Mantle クライアントで呼ぶ。認証は `terraform/.env` の
    AWS 一時認証情報（deploy と同じ）。費用は AWS の従量課金。
  - `claude-code`: Claude Code の非対話モード（`claude -p`）をサブスクリプション認証で呼ぶ。使用量は
    サブスクリプションで賄う。上限に達したら `UsageLimitError` で採点ループを止める。
  採点プロンプト・入力・JSON の読み取り・スコアの検証は両方式で共通にし、呼び出し部分（Caller）だけを差し替える。
- Bedrock の Mantle エンドポイントは `output_config.format`（構造化出力）を受け付けないため、採点プロンプトで
  JSON だけを返すよう指示し、受け取った文字列から JSON オブジェクトを取り出す。取り出せなければ1回だけ再試行する。
  採点の条件をそろえるため、`claude-code` でも構造化出力（`--json-schema`）は使わない。
- 安全分類器による拒否（stop_reason=refusal）は Opus 4.8 で1回だけ再試行する（Bedrock ではサーバー側の
  フォールバックが使えないため手動で行う）。それでも採点できなければ、その質問は「採点不可」として記録する。
- 採点のトークン数は呼び出しごとの使用量を合計して結果に残し、`evals/judge_prices.json` の単価で
  費用を概算する（ADR-0100）。思考トークンは `output_tokens` に含まれる。`claude-code` の費用は API 単価換算で、
  実際の請求額ではない。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

BACKENDS = ("bedrock", "claude-code")
# バックエンドごとの採点モデル・フォールバックモデル（Bedrock は anthropic. 接頭辞付きの ID）。
DEFAULT_MODELS = {"bedrock": "anthropic.claude-opus-5-5", "claude-code": "claude-opus-5-5"}
FALLBACK_MODELS = {"bedrock": "anthropic.claude-opus-4-8", "claude-code": "claude-opus-4-8"}
DEFAULT_MODEL = DEFAULT_MODELS["bedrock"]
FALLBACK_MODEL = FALLBACK_MODELS["bedrock"]
EFFORT = "medium"
MAX_TOKENS = 16000
PROMPT_FILE = Path(__file__).resolve().parent.parent / "judge_prompts" / "answer.md"
PRICES_FILE = Path(__file__).resolve().parent.parent / "judge_prices.json"
USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def load_aws_credentials(env_file: Path) -> None:
    """terraform/.env の AWS 認証情報を環境変数に載せる（空の AWS_PROFILE は botocore を誤動作させるため外す）。"""
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_REGION") and value:
            os.environ[key] = value
    if not os.environ.get("AWS_PROFILE"):
        os.environ.pop("AWS_PROFILE", None)


def parse_json_object(text: str) -> dict | None:
    """応答文字列から最初の JSON オブジェクトを取り出す（コードフェンスや前置きが付いても読む）。"""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def load_prices(path: Path = PRICES_FILE) -> dict:
    """採点モデルの単価表（USD / 100万トークン）。無ければ空（費用は計算しない）。"""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _usage(response) -> dict:
    """response.usage のトークン数（無い・None の項目は 0）。thinking_tokens は output_tokens の内数。"""
    usage = getattr(response, "usage", None)
    counts = {key: int(getattr(usage, key, 0) or 0) for key in USAGE_FIELDS}
    details = getattr(usage, "output_tokens_details", None)
    counts["thinking_tokens"] = int(getattr(details, "thinking_tokens", 0) or 0)
    return counts


def call_cost_usd(model: str, usage: dict, prices: dict) -> float | None:
    """1回の呼び出しの概算費用。単価表にモデルが無ければ None。"""
    price = (prices.get("models") or {}).get(model)
    if not price:
        return None
    return (usage["input_tokens"] * price["input"]
            + usage["output_tokens"] * price["output"]
            + usage["cache_creation_input_tokens"] * price["cache_write"]
            + usage["cache_read_input_tokens"] * price["cache_read"]) / 1_000_000


def _score(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        score = int(value)
    except (TypeError, ValueError):
        return None
    return score if 1 <= score <= 5 else None


class JudgeAbort(Exception):
    """以降の質問も採点できない状態（使用量の上限・認証の失敗）。採点ループを止めるため例外にする。"""

    label = "採点の中断"


class UsageLimitError(JudgeAbort):
    """サブスクリプションの使用量の上限に達した（リセットまで採点を続けられない）。"""

    label = "使用量の上限"


class JudgeAuthError(JudgeAbort):
    """認証に失敗した（claude auth status はトークンの有効性までは確かめないため、最初の呼び出しで分かる）。"""

    label = "認証の失敗"


class JudgeSetupError(Exception):
    """採点を始められない（CLI が無い・認証方式が想定と違う など）。"""


@dataclass
class Reply:
    """1回の呼び出しの結果（バックエンド共通の形）。usages はモデルごとのトークン数（claude -p は複数モデルを返しうる）。"""

    stop_reason: str
    text: str
    usages: list
    extra: dict = field(default_factory=dict)


class BedrockCaller:
    """Amazon Bedrock（Mantle）の Messages API で呼ぶ。"""

    def __init__(self, prompt: str, client=None, region: str | None = None):
        if client is None:
            import anthropic  # 評価ランナーのイメージにのみ入っている（pull-feedback では不要）

            client = anthropic.AnthropicBedrockMantle(aws_region=region or os.environ.get("AWS_REGION", "us-east-1"))
        self._client = client
        self._prompt = prompt

    def meta(self) -> dict:
        return {}

    def call(self, model: str, payload: str) -> Reply:
        response = self._client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT},
            system=self._prompt,
            messages=[{"role": "user", "content": payload}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return Reply(response.stop_reason, text, [{"model": model, **_usage(response)}])


# claude -p の子プロセスから外す環境変数。API キーやクラウド事業者の設定が残っていると、サブスクリプションでは
# なく API・Bedrock に課金が切り替わる（-p では ANTHROPIC_API_KEY が必ず優先される）。effort の環境変数は
# --effort より優先されるため外す。ランナーが載せる AWS の認証情報も渡さない。
CLAUDE_CODE_BLOCKED_ENV = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_EFFORT_LEVEL",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE", "AWS_BEARER_TOKEN_BEDROCK",
)
# claude auth status の authMethod のうち、サブスクリプションの認証とみなす値。
SUBSCRIPTION_AUTH_METHODS = ("claude.ai", "oauth_token")
CLAUDE_CODE_TIMEOUT_SEC = 600
# 使用量の上限を示すエラー文（例: "You've hit your session limit · resets 3:45pm"）。
USAGE_LIMIT_PATTERN = re.compile(r"hit your .{0,40}limit|(usage|session|weekly|rate)[ _-]?limit", re.I)


def claude_code_env(oauth_token: str | None, base: dict | None = None) -> dict:
    """claude -p に渡す環境変数（課金経路を変えうる変数を外し、サブスクリプションのトークンを載せる）。"""
    source = os.environ if base is None else base
    env = {k: v for k, v in source.items() if k not in CLAUDE_CODE_BLOCKED_ENV}
    if oauth_token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
    env["DISABLE_AUTOUPDATER"] = "1"
    return env


class ClaudeCodeCaller:
    """Claude Code の非対話モード（claude -p）で呼ぶ（ADR-0101）。1問ごとに新しいプロセスを起動する。"""

    def __init__(self, prompt: str, env: dict, cli: str = "claude", run=subprocess.run):
        self._env = env
        self._cli = cli
        self._run = run
        self.cli_version: str | None = None
        # 採点プロンプトは改行を LF にそろえた内容を渡す（prompt_hash と同じ内容にするため）。
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", suffix=".md", delete=False)
        with handle:
            handle.write(prompt)
        self.prompt_path = handle.name

    def meta(self) -> dict:
        return {"cli_version": self.cli_version}

    def _exec(self, args: list, payload: str | None = None, timeout: int = 60):
        try:
            return self._run([self._cli, *args], input=payload, capture_output=True, text=True, encoding="utf-8",
                             env=self._env, timeout=timeout)
        except FileNotFoundError as exc:
            raise JudgeSetupError(f"{self._cli} が見つかりません（evals/Dockerfile で Claude Code を入れています）") from exc

    def preflight(self) -> None:
        """採点の前に CLI の版と認証方式を確かめる。サブスクリプション以外の認証なら中止する。"""
        version = self._exec(["--version"])
        self.cli_version = (version.stdout or "").strip() or None
        status = self._exec(["auth", "status"])
        try:
            method = json.loads(status.stdout or "").get("authMethod")
        except (json.JSONDecodeError, AttributeError):
            method = None
        if method not in SUBSCRIPTION_AUTH_METHODS:
            output = (status.stdout or status.stderr or "").strip()[:300]
            raise JudgeSetupError(
                f"Claude Code がサブスクリプションで認証されていません（authMethod={method!r}）。"
                "claude setup-token で発行したトークンを evals/.env の CLAUDE_CODE_OAUTH_TOKEN に書いてください。"
                f" claude auth status の出力: {output}")

    def call(self, model: str, payload: str) -> Reply:
        args = ["--safe-mode", "-p", "--tools", "", "--max-turns", "1", "--no-session-persistence",
                "--system-prompt-file", self.prompt_path, "--model", model, "--effort", EFFORT,
                "--output-format", "json"]
        proc = self._exec(args, payload, timeout=CLAUDE_CODE_TIMEOUT_SEC)
        try:
            data = json.loads(proc.stdout or "")
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            message = f"{proc.stdout or ''} {proc.stderr or ''}".strip()
            if USAGE_LIMIT_PATTERN.search(message):
                raise UsageLimitError(message[:300])
            raise RuntimeError(f"claude -p が失敗しました（終了コード {proc.returncode}）: {message[:300]}")
        text = str(data.get("result") or "")
        if data.get("is_error") or data.get("subtype") not in (None, "success"):
            # API の失敗は is_error=true・api_error_status に HTTP ステータスが入る（subtype は success のまま）。
            status = data.get("api_error_status")
            if status == 429 or USAGE_LIMIT_PATTERN.search(text):
                raise UsageLimitError(text[:300])
            if status in (401, 403):
                raise JudgeAuthError(f"{text[:300]}（evals/.env の CLAUDE_CODE_OAUTH_TOKEN を確かめてください）")
            raise RuntimeError(f"claude -p がエラーを返しました（{data.get('subtype')}, {status}）: {text[:300]}")
        return Reply(str(data.get("stop_reason") or "end_turn"), text, _claude_code_usages(data, model),
                     {"total_cost_usd": data.get("total_cost_usd")})


def _claude_code_usages(data: dict, model: str) -> list:
    """claude -p の JSON からモデルごとのトークン数を取り出す（modelUsage が無ければ usage を要求モデルの分とする）。
    思考トークンは usage.output_tokens_details にしか無いため、要求モデル（無ければ先頭）の分として付ける。"""
    usage = data.get("usage") or {}
    thinking = int((usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
    by_model = data.get("modelUsage") or {}
    if not by_model:
        counts = {key: int(usage.get(key) or 0) for key in USAGE_FIELDS}
        return [{"model": model, **counts, "thinking_tokens": thinking}]
    names = sorted(by_model, key=lambda name: name != model)  # 要求モデルを先頭にする（呼び出し回数の n=1 を付ける）
    return [{
        "model": name,
        "input_tokens": int(by_model[name].get("inputTokens") or 0),
        "output_tokens": int(by_model[name].get("outputTokens") or 0),
        "cache_creation_input_tokens": int(by_model[name].get("cacheCreationInputTokens") or 0),
        "cache_read_input_tokens": int(by_model[name].get("cacheReadInputTokens") or 0),
        "thinking_tokens": thinking if i == 0 else 0,
    } for i, name in enumerate(names)]


class Judge:
    def __init__(self, model: str | None = None, region: str | None = None, prompt_file: Path = PROMPT_FILE,
                 client=None, prices: dict | None = None, backend: str = "bedrock", caller=None):
        if backend not in BACKENDS:
            raise ValueError(f"未知の採点バックエンド: {backend}")
        self.backend = backend
        model = model or os.environ.get("EVAL_JUDGE_MODEL_ID") or DEFAULT_MODELS[backend]
        if backend == "claude-code" and model.startswith("anthropic."):
            model = model[len("anthropic."):]  # Claude Code は Anthropic API の ID（接頭辞なし）を使う
        self.model = model
        self.fallback_model = FALLBACK_MODELS[backend]
        self.prompt = prompt_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.prompt_hash = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()[:16]
        self.prompt_file = prompt_file
        self.prices = load_prices() if prices is None else prices
        if caller is None:
            if backend != "bedrock":
                raise ValueError("claude-code バックエンドは ClaudeCodeCaller を渡して作る（make_judge を使う）")
            caller = BedrockCaller(self.prompt, client=client, region=region)
        self._caller = caller

    def meta(self) -> dict:
        return {"model": self.model, "fallback_model": self.fallback_model, "effort": EFFORT,
                "prompt_file": "evals/judge_prompts/" + self.prompt_file.name, "prompt_hash": self.prompt_hash,
                "backend": self.backend, **self._caller.meta()}

    def _call(self, model: str, payload: str, calls: list) -> Reply:
        """1回呼び出し、応答が返ればトークン数を calls に積む（拒否・JSON 読み取り失敗の応答も課金されるため）。
        1回の呼び出しで複数モデルの使用量が返ることがあるため、呼び出し回数は n（先頭だけ 1）で数える。"""
        reply = self._caller.call(model, payload)
        for i, usage in enumerate(reply.usages):
            calls.append({**usage, "n": 1 if i == 0 else 0})
        return reply

    def _usage_fields(self, calls: list) -> dict:
        """1問分の採点の呼び出し回数・トークン数・概算費用（単価表に無いモデルを含めば費用は None）。"""
        costs = [call_cost_usd(c["model"], c, self.prices) for c in calls]
        return {
            "judge_calls": sum(c["n"] for c in calls),
            "judge_input_tokens": sum(c["input_tokens"] for c in calls),
            "judge_output_tokens": sum(c["output_tokens"] for c in calls),
            "judge_thinking_tokens": sum(c["thinking_tokens"] for c in calls),
            "judge_cache_write_tokens": sum(c["cache_creation_input_tokens"] for c in calls),
            "judge_cache_read_tokens": sum(c["cache_read_input_tokens"] for c in calls),
            "judge_cost_usd": None if any(c is None for c in costs) else round(sum(costs), 6),
        }

    def score(self, question: str, should_answer: bool, reference_answer: str | None,
              retrieved_context: str | None, answer: str | None) -> dict:
        """スコア・採点理由・採点モデル・エラーと、採点のトークン数・概算費用を返す。
        API エラー等は例外にせず採点不可として返すが、以降も採点できない状態（JudgeAbort: 使用量の上限・認証の失敗）
        だけは呼び出し元へ伝える。"""
        payload = json.dumps({
            "question": question,
            "should_answer": should_answer,
            "reference_answer": reference_answer,
            "retrieved_context": retrieved_context or "",
            "answer": answer or "",
        }, ensure_ascii=False, indent=2)
        last_error = None
        calls: list = []
        model = self.model
        for _ in range(2):  # API エラー・JSON の読み取り失敗は1回だけ再試行する
            try:
                reply = self._call(model, payload, calls)
                if reply.stop_reason == "refusal" and model != self.fallback_model:
                    # 拒否は同じモデルで再試行しても変わらないため、フォールバックモデルに切り替える。
                    model = self.fallback_model
                    reply = self._call(model, payload, calls)
            except JudgeAbort:
                raise
            except Exception as exc:  # noqa: BLE001 - API エラーは記録して再試行・採点不可にする
                last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
                continue
            if reply.stop_reason == "refusal":
                last_error = f"refusal ({model})"
                break
            parsed = parse_json_object(reply.text)
            if parsed is None:
                last_error = f"JSON を読み取れません ({model}): {reply.text[:200]}"
                continue
            declined = parsed.get("declined")
            return {
                "correctness": _score(parsed.get("correctness")) if should_answer else None,
                "faithfulness": _score(parsed.get("faithfulness")),
                # 回答を控えた（断り・逆質問）かの LLM 判定。決定的な判定と OR で合わせる（run.py）。
                "judge_declined": declined if isinstance(declined, bool) else None,
                "judge_reason": str(parsed.get("reason") or ""),
                "judge_model": model,
                "judge_error": None,
                **self._usage_fields(calls),
            }
        return {"correctness": None, "faithfulness": None, "judge_declined": None, "judge_reason": "",
                "judge_model": None, "judge_error": last_error, **self._usage_fields(calls)}


def make_judge(backend: str, model: str | None, oauth_token: str | None = None, cli: str = "claude",
               run=subprocess.run) -> Judge:
    """バックエンドに応じた Judge を作る。claude-code は実行前に認証方式を確かめる（JudgeSetupError で中止）。"""
    if backend == "claude-code":
        prompt = PROMPT_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
        caller = ClaudeCodeCaller(prompt, claude_code_env(oauth_token), cli=cli, run=run)
        caller.preflight()
        return Judge(model=model, backend=backend, caller=caller)
    return Judge(model=model, backend=backend)
