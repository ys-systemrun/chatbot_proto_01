"""人手評価の取り込み（ADR-0099 §5 `pull-feedback`）。

admin_ui の `/api/evaluated_messages` から評価済みの回答（👍/👎）を取得し、質問・回答・理由・
リリースを1行1件の JSON にして `evals/feedback/<日時>.jsonl` に保存する。既に取り込んだもの
（会話・順序・評価・理由・評価日時が同じもの）は書かないので、何度実行しても増分だけが増える。
評価や理由を付け直したものは、新しい行として追記される（変更の履歴が残る）。

標準ライブラリのみで動く（評価ランナー用のイメージを持たないため）。
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime
from pathlib import Path

EVALUATION_LABELS = {1: "good", 2: "bad"}
ROLE_USER = 1
ROLE_ASSISTANT = 2

_CONTEXT_HEAD = "参考情報:\n"
_QUESTION_HEAD = "\n\n質問:\n"


def split_user_content(content: str | None) -> tuple[str, str | None]:
    """user メッセージ（`参考情報:\\n{context}\\n\\n質問:\\n{text}` 形式）を (質問, 参考情報) に分ける。

    形式に合わない（ローカル方式の回答など）ときは本文全体を質問とみなす。
    """
    content = content or ""
    if content.startswith(_CONTEXT_HEAD) and _QUESTION_HEAD in content:
        context, _, question = content[len(_CONTEXT_HEAD):].rpartition(_QUESTION_HEAD)
        return question, context
    return content, None


def feedback_key(row: dict) -> str:
    raw = json.dumps(
        [row["conversation_id"], row["order"], row["evaluation"], row["evaluation_comment"], row["evaluated_at"]],
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def flatten(conversations: list[dict]) -> list[dict]:
    """評価済み（👍/👎）の assistant メッセージを、直前の質問と組にした行へ変換する。"""
    rows: list[dict] = []
    for conv in conversations:
        messages = sorted(conv.get("messages", []), key=lambda m: m["order"])
        by_order = {m["order"]: m for m in messages}
        for m in messages:
            label = EVALUATION_LABELS.get(m.get("evaluation"))
            if m.get("role") != ROLE_ASSISTANT or label is None:
                continue
            user = by_order.get(m["order"] - 1)
            question, context = split_user_content(user.get("content") if user and user.get("role") == ROLE_USER else None)
            row = {
                "conversation_id": conv["id"],
                "order": m["order"],
                "evaluation": label,
                "evaluation_comment": m.get("evaluation_comment"),
                "evaluated_at": m.get("evaluated_at"),
                "answered_at": m.get("created_at"),
                "question": question,
                "context": context,
                "answer": m.get("content"),
                "model": m.get("model"),
                "ask_mode": m.get("ask_mode"),
                "release_id": m.get("release_id"),
                "release": m.get("release"),
            }
            row["key"] = feedback_key(row)
            rows.append(row)
    return rows


def known_keys(feedback_dir: Path) -> set[str]:
    keys: set[str] = set()
    for path in sorted(feedback_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                keys.add(json.loads(line)["key"])
    return keys


def fetch_evaluated(base_url: str, timeout: float = 60) -> list[dict]:
    url = base_url.rstrip("/") + "/api/evaluated_messages"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 社内 ALB 固定の URL
        return json.loads(resp.read().decode("utf-8"))


def pull(base_url: str, feedback_dir: Path, now: datetime | None = None, fetch=fetch_evaluated) -> Path | None:
    """増分を `<feedback_dir>/<YYYYMMDD-HHMMSS>.jsonl` に書き、そのパスを返す（増分なしは None）。"""
    feedback_dir.mkdir(parents=True, exist_ok=True)
    seen = known_keys(feedback_dir)
    new_rows = [r for r in flatten(fetch(base_url)) if r["key"] not in seen]
    if not new_rows:
        return None
    now = now or datetime.now()
    path = feedback_dir / f"{now:%Y%m%d-%H%M%S}.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in new_rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def summarize(path: Path) -> str:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    good = sum(1 for r in rows if r["evaluation"] == "good")
    bad = [r for r in rows if r["evaluation"] == "bad"]
    lines = [f"{path.name}: {len(rows)} 件（👍 {good} / 👎 {len(bad)}）"]
    for r in bad:
        reason = r["evaluation_comment"] or "（理由なし）"
        question = r["question"].replace("\n", " ")
        lines.append(f"  👎 {question[:60]} — {reason}")
    return "\n".join(lines)
