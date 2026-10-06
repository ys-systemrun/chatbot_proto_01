"""admin_ui（AWS 検証環境）への問い合わせ（ADR-0099 §5）。標準ライブラリのみ。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .feedback import split_user_content


def _request(url: str, body: dict | None = None, timeout: float = 180) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="GET" if body is None else "POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 社内 ALB 固定の URL
        return json.loads(resp.read().decode("utf-8"))


def fetch_release(base_url: str) -> dict | None:
    """現在のリリース（/api/release）。段階③以前の環境で未提供なら None。"""
    try:
        return _request(base_url.rstrip("/") + "/api/release", timeout=30)
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def ask(base_url: str, mode: str, question: str, timeout: float = 180) -> dict:
    """1問を新しい会話として送り、回答・出典・リリースを返す。失敗は error に入れて返す（例外にしない）。"""
    url = f"{base_url.rstrip('/')}/api/ask-{mode}"
    body = {"text": question, "messages": [], "summary": {"content": "", "summarized_upto": 0}}
    started = time.monotonic()
    try:
        resp = _request(url, body, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        return {"error": f"HTTP {exc.code}: {detail}", "latency_ms": int((time.monotonic() - started) * 1000)}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "latency_ms": int((time.monotonic() - started) * 1000)}
    latency_ms = int((time.monotonic() - started) * 1000)

    messages = resp.get("messages", [])
    assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), {})
    user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    _, context = split_user_content(user.get("content"))
    return {
        "answer": assistant.get("content"),
        # sources が無い（段階③以前の agent_invitro）場合は None。出典は採点しない。
        "sources": assistant.get("sources"),
        "context": context,
        "release_id": assistant.get("release_id"),
        "ask_mode": assistant.get("ask_mode"),
        "model": assistant.get("model"),
        "latency_ms": latency_ms,
        "error": None,
    }
