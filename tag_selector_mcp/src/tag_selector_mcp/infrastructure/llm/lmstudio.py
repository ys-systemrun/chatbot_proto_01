"""LMStudioLLMClient（実装指示書 5.4 / T6 / ADR-0012）。

LM Studio の Chat Completions API（OpenAI互換エンドポイント）を呼び出す。
既存 web_backend/src/llm/*.py と同一のリクエスト/レスポンス形式:
    POST {completions_url}
    body: {"model": <model>, "messages": [{"role": "user", "content": <prompt>}]}
    応答: res.json()["choices"][0]["message"]["content"]
"""

from __future__ import annotations

import requests

from .base import LLMClient

# LM Studio 応答待ちのタイムアウト（秒）。ローカルLLMは応答が遅い場合があるため長めに取る。
_DEFAULT_TIMEOUT_SEC = 120


class LMStudioLLMClient(LLMClient):
    def __init__(self, base_url: str, model: str, timeout_sec: int = _DEFAULT_TIMEOUT_SEC):
        self._base_url = base_url
        self._model = model
        self._timeout_sec = timeout_sec

    def _completions_url(self) -> str:
        """Chat Completions のフルURLを組み立てる。

        設定値（LMSTUDIO_CHAT_URL）が既に `/v1/chat/completions` を含む完全URL
        （既存 .env の形式）でも、ベースURLのみ（実装指示書6章の例）でも動作させる。
        """
        base = self._base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/v1/chat/completions"

    def complete(self, prompt: str) -> str:
        res = requests.post(
            self._completions_url(),
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self._timeout_sec,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]
