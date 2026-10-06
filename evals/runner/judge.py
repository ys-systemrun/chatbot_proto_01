"""LLM 採点（ADR-0099 §5）。Amazon Bedrock 上の Claude を Anthropic SDK（Bedrock Mantle クライアント）で呼ぶ。

- 採点モデルは回答用モデル（Amazon Nova）とは別。既定は Claude Opus 5.5（`EVAL_JUDGE_MODEL_ID` で変更可）。
- Bedrock の Mantle エンドポイントは `output_config.format`（構造化出力）を受け付けないため、採点プロンプトで
  JSON だけを返すよう指示し、受け取った文字列から JSON オブジェクトを取り出す。取り出せなければ1回だけ再試行する。
- 安全分類器による拒否（stop_reason=refusal）は Opus 4.8 で1回だけ再試行する（Bedrock ではサーバー側の
  フォールバックが使えないため手動で行う）。それでも採点できなければ、その質問は「採点不可」として記録する。
- 認証は `terraform/.env` の AWS 一時認証情報（deploy と同じ）。
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
                 client=None):
        self.model = model or os.environ.get("EVAL_JUDGE_MODEL_ID") or DEFAULT_MODEL
        self.prompt = prompt_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.prompt_hash = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()[:16]
        self.prompt_file = prompt_file
        if client is None:
            import anthropic  # 評価ランナーのイメージにのみ入っている（pull-feedback では不要）

            client = anthropic.AnthropicBedrockMantle(aws_region=region or os.environ.get("AWS_REGION", "us-east-1"))
        self._client = client

    def meta(self) -> dict:
        return {"model": self.model, "fallback_model": FALLBACK_MODEL, "effort": EFFORT,
                "prompt_file": "evals/judge_prompts/" + self.prompt_file.name, "prompt_hash": self.prompt_hash}

    def _call(self, model: str, payload: str):
        return self._client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT},
            system=self.prompt,
            messages=[{"role": "user", "content": payload}],
        )

    def score(self, question: str, should_answer: bool, reference_answer: str | None,
              retrieved_context: str | None, answer: str | None) -> dict:
        """{"correctness", "faithfulness", "reason", "judge_model", "judge_error"} を返す（例外にしない）。"""
        payload = json.dumps({
            "question": question,
            "should_answer": should_answer,
            "reference_answer": reference_answer,
            "retrieved_context": retrieved_context or "",
            "answer": answer or "",
        }, ensure_ascii=False, indent=2)
        last_error = None
        model = self.model
        for _ in range(2):  # API エラー・JSON の読み取り失敗は1回だけ再試行する
            try:
                response = self._call(model, payload)
                if response.stop_reason == "refusal" and model != FALLBACK_MODEL:
                    # 拒否は同じモデルで再試行しても変わらないため、フォールバックモデルに切り替える。
                    model = FALLBACK_MODEL
                    response = self._call(model, payload)
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
            }
        return {"correctness": None, "faithfulness": None, "judge_declined": None, "judge_reason": "",
                "judge_model": None, "judge_error": last_error}
