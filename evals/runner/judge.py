"""LLM 採点（ADR-0099 §5）。Amazon Bedrock 上の Claude を Anthropic SDK（Bedrock Mantle クライアント）で呼ぶ。

- 採点モデルは回答用モデル（Amazon Nova）とは別。既定は Claude Opus 5.5（`EVAL_JUDGE_MODEL_ID` で変更可）。
- Bedrock の Mantle エンドポイントは `output_config.format`（構造化出力）を受け付けないため、採点プロンプトで
  JSON だけを返すよう指示し、受け取った文字列から JSON オブジェクトを取り出す。取り出せなければ1回だけ再試行する。
- 安全分類器による拒否（stop_reason=refusal）は Opus 4.8 で1回だけ再試行する（Bedrock ではサーバー側の
  フォールバックが使えないため手動で行う）。それでも採点できなければ、その質問は「採点不可」として記録する。
- 認証は `terraform/.env` の AWS 一時認証情報（deploy と同じ）。
- 採点のトークン数は呼び出しごとの `response.usage` を合計して結果に残し、`evals/judge_prices.json` の単価で
  費用を概算する（ADR-0100）。思考トークンは `output_tokens` に含まれる。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

DEFAULT_MODEL = "anthropic.claude-opus-5-5"
FALLBACK_MODEL = "anthropic.claude-opus-4-8"
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


class Judge:
    def __init__(self, model: str | None = None, region: str | None = None, prompt_file: Path = PROMPT_FILE,
                 client=None, prices: dict | None = None):
        self.model = model or os.environ.get("EVAL_JUDGE_MODEL_ID") or DEFAULT_MODEL
        self.prompt = prompt_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.prompt_hash = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()[:16]
        self.prompt_file = prompt_file
        self.prices = load_prices() if prices is None else prices
        if client is None:
            import anthropic  # 評価ランナーのイメージにのみ入っている（pull-feedback では不要）

            client = anthropic.AnthropicBedrockMantle(aws_region=region or os.environ.get("AWS_REGION", "us-east-1"))
        self._client = client

    def meta(self) -> dict:
        return {"model": self.model, "fallback_model": FALLBACK_MODEL, "effort": EFFORT,
                "prompt_file": "evals/judge_prompts/" + self.prompt_file.name, "prompt_hash": self.prompt_hash}

    def _call(self, model: str, payload: str, calls: list):
        """1回呼び出し、応答が返ればトークン数を calls に積む（拒否・JSON 読み取り失敗の応答も課金されるため）。"""
        response = self._client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT},
            system=self.prompt,
            messages=[{"role": "user", "content": payload}],
        )
        calls.append({"model": model, **_usage(response)})
        return response

    def _usage_fields(self, calls: list) -> dict:
        """1問分の採点の呼び出し回数・トークン数・概算費用（単価表に無いモデルを含めば費用は None）。"""
        costs = [call_cost_usd(c["model"], c, self.prices) for c in calls]
        return {
            "judge_calls": len(calls),
            "judge_input_tokens": sum(c["input_tokens"] for c in calls),
            "judge_output_tokens": sum(c["output_tokens"] for c in calls),
            "judge_thinking_tokens": sum(c["thinking_tokens"] for c in calls),
            "judge_cache_write_tokens": sum(c["cache_creation_input_tokens"] for c in calls),
            "judge_cache_read_tokens": sum(c["cache_read_input_tokens"] for c in calls),
            "judge_cost_usd": None if any(c is None for c in costs) else round(sum(costs), 6),
        }

    def score(self, question: str, should_answer: bool, reference_answer: str | None,
              retrieved_context: str | None, answer: str | None) -> dict:
        """スコア・採点理由・採点モデル・エラーと、採点のトークン数・概算費用を返す（例外にしない）。"""
        payload = json.dumps({
            "question": question,
            "should_answer": should_answer,
            "reference_answer": reference_answer,
            "retrieved_context": retrieved_context or "",
            "answer": answer or "",
        }, ensure_ascii=False, indent=2)
        last_error = None
        calls: list[dict] = []
        model = self.model
        for _ in range(2):  # API エラー・JSON の読み取り失敗は1回だけ再試行する
            try:
                response = self._call(model, payload, calls)
                if response.stop_reason == "refusal" and model != FALLBACK_MODEL:
                    # 拒否は同じモデルで再試行しても変わらないため、フォールバックモデルに切り替える。
                    model = FALLBACK_MODEL
                    response = self._call(model, payload, calls)
            except Exception as exc:  # noqa: BLE001 - API エラーは記録して再試行・採点不可にする
                last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
                continue
            if response.stop_reason == "refusal":
                last_error = f"refusal ({model})"
                break
            text = "".join(b.text for b in response.content if b.type == "text")
            parsed = parse_json_object(text)
            if parsed is None:
                last_error = f"JSON を読み取れません ({model}): {text[:200]}"
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
