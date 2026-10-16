"""同じ構成の繰り返し実行と、揺れを考慮した比較（ADR-0099 §5 の拡張）。

回答（Amazon Nova）は temperature 0 でも毎回変わり、LLM 採点も揺れる。v2 で同じ構成を2回実行すると、
出典の一致率はほぼ同じでも、回答の正しさは ±0.3、回答を控えた割合は ±0.1 程度動いた。
1回ずつの比較ではこの揺れと改善の効果を区別できないため、`run --repeat N` で同じ構成を N 回実行し、
指標の平均とばらつきで比べる。

- 繰り返しの各回は通常の実行ディレクトリ（`<日時>_<セット>_<方式>_r<回>`）として保存し、meta.json の
  `repeat` に同じグループ ID を入れる。採点の続き（judge --only-missing）や history.csv は各回のまま使える。
- グループの集計は `evals/runs/groups/<グループ ID>.md` に書く。
- 比較（compare）は実行ディレクトリ名かグループ ID を受け取る。指標の差は、両側のばらつきから求めた
  標準誤差の2倍を超えたときだけ「揺れを超える差」とする。質問単位では、片側の全回がもう片側の全回より
  良い（悪い）ときだけ改善（悪化）とする。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import scoring

GROUPS_DIR = "groups"

# 揺れの判定に使う指標（集計表に出す順）。
COMPARED_METRICS = [
    (key, label, direction) for key, label, direction in scoring.METRIC_LABELS if direction is not None
]


def group_id(started, golden_name: str, mode: str, count: int) -> str:
    return f"{started:%Y%m%d-%H%M%S}_{golden_name}_{mode}_x{count}"


def find_group(runs_dir: Path, gid: str) -> list[Path]:
    """グループ ID に属する実行ディレクトリ（回の順）。"""
    found = []
    for meta_path in runs_dir.glob("*/meta.json"):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        rep = meta.get("repeat") or {}
        if rep.get("group") == gid:
            found.append((rep.get("index") or 0, meta_path.parent))
    return [path for _, path in sorted(found)]


def resolve(runs_dir: Path, name: str) -> tuple[str, list[Path]]:
    """実行ディレクトリ名・パスかグループ ID を、(表示名, 実行ディレクトリの一覧) にする。見つからなければ空。"""
    path = Path(name)
    if not path.is_absolute() and not path.exists():
        path = runs_dir / name
    if (path / "results.jsonl").exists():
        return path.name, [path]
    return name, find_group(runs_dir, name)


def stats(values: list[float]) -> dict | None:
    """平均・標準偏差（標本, n-1）・最小・最大・回数。値が無ければ None。"""
    values = [v for v in values if v is not None]
    if not values:
        return None
    n = len(values)
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else None
    return {"mean": round(mean, 3), "sd": None if sd is None else round(sd, 3),
            "min": min(values), "max": max(values), "n": n}


def metric_stats(runs_rows: list[list[dict]]) -> dict[str, dict | None]:
    """各回の集計値から、指標ごとの平均とばらつきを求める。"""
    per_run = [scoring.aggregate(rows) for rows in runs_rows]
    return {key: stats([agg.get(key) for agg in per_run]) for key, _, _ in COMPARED_METRICS}


def _fmt(s: dict | None) -> str:
    if s is None:
        return "－"
    if s["n"] == 1:
        return f"{s['mean']}"
    return f"{s['mean']} ± {s['sd']}（{s['min']}〜{s['max']}）"


def noise_threshold(a: dict | None, b: dict | None) -> float | None:
    """差を「揺れを超える」とみなす目安（標準誤差の2倍）。片側しかばらつきが分からなければその値で両側を代用する。"""
    if a is None or b is None:
        return None
    sd_a, sd_b = a["sd"], b["sd"]
    if sd_a is None and sd_b is None:
        return None
    sd_a = sd_b if sd_a is None else sd_a
    sd_b = sd_a if sd_b is None else sd_b
    return round(2 * math.sqrt(sd_a ** 2 / a["n"] + sd_b ** 2 / b["n"]), 3)


def question_value(row: dict) -> float | None:
    """質問1回分の良し悪しを1つの数値にする（大きいほど良い）。エラーは None。
    回答すべき質問は正しさ（未採点なら出典の順位から 5/3/1）、控えたら 1。範囲外の質問は控えたら 5、答えたら 1。"""
    if row.get("error"):
        return None
    if not row["should_answer"]:
        return 5.0 if row["declined"] else 1.0
    if row["declined"]:
        return 1.0
    if row.get("correctness") is not None:
        return float(row["correctness"])
    rank = row.get("source_rank")
    if rank is None:
        return None
    return 5.0 if rank == 1 else 3.0 if rank else 1.0


def question_values(runs_rows: list[list[dict]]) -> dict[str, list[float]]:
    """質問 ID ごとの各回の値（エラーの回は除く）。"""
    values: dict[str, list[float]] = {}
    for rows in runs_rows:
        for row in rows:
            v = question_value(row)
            if v is not None:
                values.setdefault(row["id"], []).append(v)
    return values


def compare_questions(before: list[list[dict]], after: list[list[dict]]) -> dict:
    """質問単位の比較。全回がもう片側の全回より良い／悪いときだけ改善／悪化とする。"""
    b_vals, a_vals = question_values(before), question_values(after)
    result = {"better": [], "worse": [], "unclear": [], "same": []}
    for qid in sorted(set(b_vals) & set(a_vals)):
        b, a = b_vals[qid], a_vals[qid]
        if min(a) > max(b):
            result["better"].append((qid, b, a))
        elif max(a) < min(b):
            result["worse"].append((qid, b, a))
        elif sorted(a) == sorted(b) and len(set(a)) == 1:
            result["same"].append((qid, b, a))
        else:
            result["unclear"].append((qid, b, a))
    return result


def _questions_text(runs_rows: list[list[dict]]) -> dict[str, str]:
    return {row["id"]: row["question"] for rows in runs_rows for row in rows}


def compare_markdown(before_name: str, before: list[list[dict]], after_name: str, after: list[list[dict]]) -> str:
    b_stats, a_stats = metric_stats(before), metric_stats(after)
    lines = [f"## 比較: `{before_name}`（{len(before)} 回）→ `{after_name}`（{len(after)} 回）", ""]
    if len(before) == 1 and len(after) == 1:
        lines += ["> 両側とも1回ずつのため、差が揺れによるものか区別できません（`run --repeat 3` を推奨）。"
                  "過去の再実行では、出典の一致率はほぼ同じ、回答の正しさは ±0.3、回答を控えた割合は ±0.1 程度動いた。", ""]
    lines += ["| 指標 | 変更前 | 変更後 | 差 | 揺れの目安 | 判定 |", "|---|---|---|---|---|---|"]
    for key, label, direction in COMPARED_METRICS:
        b, a = b_stats.get(key), a_stats.get(key)
        if b is None or a is None:
            lines.append(f"| {label} | {_fmt(b)} | {_fmt(a)} | － | － | － |")
            continue
        diff = round(a["mean"] - b["mean"], 3)
        threshold = noise_threshold(b, a)
        if threshold is None:
            verdict = "判定不可（1回ずつ）"
        elif abs(diff) <= threshold:
            verdict = "揺れの範囲内"
        else:
            good = diff > 0 if direction == "higher" else diff < 0
            verdict = "**改善**" if good else "**悪化**"
        lines.append(f"| {label} | {_fmt(b)} | {_fmt(a)} | {diff:+} | {'－' if threshold is None else threshold} | {verdict} |")

    q = compare_questions(before, after)
    texts = _questions_text(after) or _questions_text(before)
    lines += ["", f"質問単位（全回が反対側の全回を上回る／下回るときだけ判定）: 改善 {len(q['better'])} / 悪化 {len(q['worse'])}"
                  f" / どちらとも言えない {len(q['unclear'])} / 変化なし {len(q['same'])}"]
    for key, title in (("worse", "悪化した質問"), ("better", "改善した質問")):
        if q[key]:
            lines += ["", f"### {title}", "", "| ID | 質問 | 変更前（各回） | 変更後（各回） |", "|---|---|---|---|"]
            for qid, b, a in q[key]:
                question = texts.get(qid, "").replace("|", "｜").replace("\n", " ")[:50]
                lines.append(f"| {qid} | {question} | {b} | {a} |")
    lines += ["", "質問の値: 回答すべき質問は正しさ（1〜5、控えたら 1）、範囲外の質問は控えたら 5・答えたら 1。"]
    return "\n".join(lines) + "\n"


def group_markdown(gid: str, run_dirs: list[Path], runs_rows: list[list[dict]], metas: list[dict]) -> str:
    """グループ（同じ構成の N 回）の集計。指標の平均とばらつき、回ごとに結果が変わった質問、採点の費用の合計。"""
    first = metas[0]
    release = first.get("release") or {}
    st = metric_stats(runs_rows)
    lines = [
        f"# 繰り返し評価: {gid}",
        "",
        f"- ゴールデンセット: `{first['golden']['path']}`（{first['golden']['count']} 問）／方式: {first['mode']}／{len(run_dirs)} 回",
        f"- リリース: `{release.get('release_id') or '不明'}`（commit `{release.get('git_commit') or '不明'}`）",
        "- 各回: " + "、".join(f"`{d.name}`" for d in run_dirs),
        "",
        "## 指標（平均 ± 標準偏差（最小〜最大））",
        "",
        "| 指標 | 値 |",
        "|---|---|",
    ]
    lines += [f"| {label} | {_fmt(st.get(key))} |" for key, label, _ in COMPARED_METRICS]

    costs = [scoring.judge_usage(rows).get("judge_cost_usd") for rows in runs_rows]
    if any(c is not None for c in costs):
        total = None if any(c is None for c in costs) else round(sum(costs), 4)
        lines += ["", f"採点の概算費用（{len(runs_rows)} 回の合計, USD）: {total if total is not None else '一部の回で不明'}"]

    values = question_values(runs_rows)
    texts = _questions_text(runs_rows)
    unstable = [(qid, v) for qid, v in sorted(values.items()) if max(v) - min(v) >= 2]
    lines += ["", f"## 回ごとに結果が大きく変わった質問（値の幅が2以上）: {len(unstable)} 問", ""]
    if unstable:
        lines += ["| ID | 質問 | 各回の値 |", "|---|---|---|"]
        for qid, v in unstable:
            lines.append(f"| {qid} | {texts.get(qid, '').replace('|', '｜').replace(chr(10), ' ')[:50]} | {v} |")
    lines += ["", "質問の値: 回答すべき質問は正しさ（1〜5、控えたら 1）、範囲外の質問は控えたら 5・答えたら 1。"
                  "このグループを比較の基準にするときは `evals\\eval.bat compare " + gid + " <変更後のグループ>` を使う。"]
    return "\n".join(lines) + "\n"


def write_group_summary(runs_dir: Path, gid: str, load_run) -> Path:
    run_dirs = find_group(runs_dir, gid)
    loaded = [load_run(d) for d in run_dirs]
    text = group_markdown(gid, run_dirs, [rows for rows, _ in loaded], [meta for _, meta in loaded])
    out = runs_dir / GROUPS_DIR / f"{gid}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return out
