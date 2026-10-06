"""決定的な採点・集計・実行どうしの比較（ADR-0099 §5）。"""

from __future__ import annotations

# 回答を控えたとみなす文言（agent_invitro/prompts/generate.md のルール3・4の定型文）。
DECLINE_MARKERS = (
    "ご提供いただいた情報が不足しています",
    "範疇を超えるため",
)


def source_key(source: dict) -> str:
    return f"{source.get('source_type')}:{source.get('id')}"


def source_rank(expected: list[str], sources: list[dict] | None) -> int | None:
    """正解出典のうち最上位の順位（1始まり）。出典が返らない・正解が無いときは None、見つからなければ 0。"""
    if not expected or sources is None:
        return None
    keys = [source_key(s) for s in sources]
    ranks = [keys.index(e) + 1 for e in expected if e in keys]
    return min(ranks) if ranks else 0


def is_declined(answer: str | None, sources: list[dict] | None, ask_mode: str | None) -> bool:
    """回答を控えたか（定型の断り文言、または agentic の逆質問＝出典なしで返した場合）。"""
    text = answer or ""
    if any(marker in text for marker in DECLINE_MARKERS):
        return True
    return ask_mode == "agentic" and sources == []


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def aggregate(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r.get("error")]
    answerable = [r for r in ok if r["should_answer"]]
    out_of_scope = [r for r in ok if not r["should_answer"]]
    ranked = [r for r in answerable if r.get("source_rank") is not None]
    return {
        "questions": len(rows),
        "errors": len(rows) - len(ok),
        "source_scored": len(ranked),
        "source_hit_at_1": _mean([1.0 if r["source_rank"] == 1 else 0.0 for r in ranked]),
        "source_hit_any": _mean([1.0 if r["source_rank"] else 0.0 for r in ranked]),
        "source_mrr": _mean([1.0 / r["source_rank"] if r["source_rank"] else 0.0 for r in ranked]),
        "correctness_mean": _mean([r["correctness"] for r in answerable if r.get("correctness") is not None]),
        "faithfulness_mean": _mean([r["faithfulness"] for r in ok if r.get("faithfulness") is not None]),
        "false_decline_rate": _mean([1.0 if r["declined"] else 0.0 for r in answerable]),
        "out_of_scope_decline_rate": _mean([1.0 if r["declined"] else 0.0 for r in out_of_scope]),
        "latency_ms_mean": _mean([float(r["latency_ms"]) for r in ok if r.get("latency_ms") is not None]),
    }


METRIC_LABELS = [
    ("questions", "質問数", None),
    ("errors", "エラー", "lower"),
    ("source_scored", "出典を採点した質問数", None),
    ("source_hit_at_1", "出典 1位一致率", "higher"),
    ("source_hit_any", "出典 一致率（いずれかの順位）", "higher"),
    ("source_mrr", "出典 MRR", "higher"),
    ("correctness_mean", "回答の正しさ（1〜5, LLM 採点）", "higher"),
    ("faithfulness_mean", "根拠への忠実さ（1〜5, LLM 採点）", "higher"),
    ("false_decline_rate", "回答すべき質問で控えた割合", "lower"),
    ("out_of_scope_decline_rate", "範囲外の質問で控えた割合", "higher"),
    ("latency_ms_mean", "平均応答時間（ms）", "lower"),
]


def _question_score(row: dict) -> tuple:
    """質問単位の良し悪しの比較キー（大きいほど良い）。"""
    if row.get("error"):
        return (-1,)
    if not row["should_answer"]:
        return (1 if row["declined"] else 0,)
    return (
        0 if row["declined"] else 1,
        row.get("correctness") or 0,
        (1.0 / row["source_rank"]) if row.get("source_rank") else 0.0,
    )


def compare(before: list[dict], after: list[dict]) -> dict:
    """質問 ID で突き合わせ、悪化・改善・変化なしに分ける。"""
    before_by_id = {r["id"]: r for r in before}
    changes = {"worse": [], "better": [], "same": [], "added": [], "removed": []}
    for row in after:
        prev = before_by_id.pop(row["id"], None)
        if prev is None:
            changes["added"].append(row)
            continue
        a, b = _question_score(prev), _question_score(row)
        key = "better" if b > a else "worse" if b < a else "same"
        changes[key].append((prev, row))
    changes["removed"] = list(before_by_id.values())
    return changes


def _cell(row: dict) -> str:
    if row.get("error"):
        return "エラー"
    parts = ["控えた" if row["declined"] else "回答"]
    if row.get("correctness") is not None:
        parts.append(f"正{row['correctness']}")
    if row.get("source_rank") is not None:
        parts.append(f"出典{row['source_rank'] or '×'}")
    return " / ".join(parts)


def compare_markdown(before: list[dict], after: list[dict], before_name: str, after_name: str,
                     before_meta: dict | None = None, after_meta: dict | None = None) -> str:
    agg_before, agg_after = aggregate(before), aggregate(after)
    lines = [f"## 比較: `{before_name}` → `{after_name}`", ""]
    if before_meta and after_meta:
        warnings = []
        if (before_meta.get("judge") or {}).get("prompt_hash") != (after_meta.get("judge") or {}).get("prompt_hash") or \
                (before_meta.get("judge") or {}).get("model") != (after_meta.get("judge") or {}).get("model"):
            warnings.append("採点モデルまたは採点プロンプトが異なるため、LLM 採点の差は参考値です。")
        if (before_meta.get("golden") or {}).get("sha256") != (after_meta.get("golden") or {}).get("sha256"):
            warnings.append("ゴールデンセットの内容が異なります（質問 ID で突き合わせています）。")
        lines += [f"> {w}" for w in warnings] + ([""] if warnings else [])
    lines += ["| 指標 | 変更前 | 変更後 |", "|---|---|---|"]
    for key, label, _ in METRIC_LABELS:
        lines.append(f"| {label} | {agg_before.get(key)} | {agg_after.get(key)} |")
    changes = compare(before, after)
    lines += [
        "",
        f"質問単位: 悪化 {len(changes['worse'])} / 改善 {len(changes['better'])} / 変化なし {len(changes['same'])}"
        f" / 追加 {len(changes['added'])} / 削除 {len(changes['removed'])}",
    ]
    for key, title in (("worse", "悪化した質問"), ("better", "改善した質問")):
        if changes[key]:
            lines += ["", f"### {title}", "", "| ID | 質問 | 変更前 | 変更後 | 採点理由（変更後） |", "|---|---|---|---|---|"]
            for prev, row in changes[key]:
                question = row["question"].replace("|", "｜").replace("\n", " ")[:50]
                reason = (row.get("judge_reason") or "").replace("|", "｜").replace("\n", " ")[:80]
                lines.append(f"| {row['id']} | {question} | {_cell(prev)} | {_cell(row)} | {reason} |")
    return "\n".join(lines) + "\n"
