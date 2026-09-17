"""十分性評価LLMの出力パース（純関数。Bedrockに依存せず単体テストできる, N-8.6）。"""

from __future__ import annotations

import json


def parse_assessment(text: str) -> dict | None:
    """十分性評価 LLM の出力を dict へパースする（10章 / F-6.3.8）。

    `json.loads` を試み、失敗した場合は文字列中の最初の `{` から最後の `}` までを切り出して
    再試行する（コードフェンスや前置きが混じった出力への保険）。それでも失敗した場合、または
    JSON オブジェクトでない・`sufficient` が bool でない場合は None を返す。
    """
    if not text:
        return None

    payload = None
    for candidate in _json_candidates(text):
        try:
            payload = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict):
            break
        payload = None

    if not isinstance(payload, dict):
        return None

    sufficient = payload.get("sufficient")
    if not isinstance(sufficient, bool):
        # "true"/"false" の文字列で返す実装差にも寛容に対応する。
        if isinstance(sufficient, str) and sufficient.strip().lower() in ("true", "false"):
            sufficient = sufficient.strip().lower() == "true"
        else:
            return None

    missing = payload.get("missing") or ""
    next_query = payload.get("next_query") or ""
    return {
        "sufficient": sufficient,
        "missing": str(missing).strip(),
        "next_query": str(next_query).strip(),
    }


def _json_candidates(text: str) -> list[str]:
    """パース対象の候補文字列（そのまま / 最初の `{` 〜 最後の `}`）を返す。"""
    stripped = text.strip()
    candidates = [stripped]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        sliced = stripped[start : end + 1]
        if sliced != stripped:
            candidates.append(sliced)
    return candidates
