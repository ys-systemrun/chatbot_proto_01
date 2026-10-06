"""ゴールデンセット評価の実行（ADR-0099 §5 `run` / `compare`）。

結果は `evals/runs/<日時>_<ゴールデンセット>_<方式>/` に保存する。質問・回答・参考情報を含むため
git には入れず DVC で管理する（`evals/runs.dvc`）。
  - results.jsonl : 1問1行（質問・回答・出典・各スコア・採点理由・release_id）
  - meta.json     : リリースの全要素・ゴールデンセットの版・採点側の版
  - summary.md    : 集計と、同じ条件の前回実行との比較
あわせて、数値だけの1行を `evals/history.csv`（git 管理）に追記し、git の差分で推移を追えるようにする。
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import client as client_mod
from . import golden as golden_mod
from . import scoring

MODES = ("pipeline", "agentic")

# 実行日時は日本時間で記録する（コンテナの時計は UTC のため）。
JST = timezone(timedelta(hours=9), "JST")


def now_jst() -> datetime:
    return datetime.now(JST)

# evals/history.csv の列（質問・回答などの文は含めない。数値と版だけ）。
HISTORY_COLUMNS = [
    "run_id", "started_at", "golden", "golden_sha256", "mode", "limit",
    "release_id", "git_commit", "git_dirty", "prompt_hash", "chat_model_id",
    "judge_model", "judge_prompt_hash",
] + [key for key, _, _ in scoring.METRIC_LABELS]


def append_history(path: Path, run_dir: Path, rows: list[dict], meta: dict) -> None:
    """1回の実行を1行として evals/history.csv に追記する（無ければヘッダーから作る）。"""
    release = meta.get("release") or {}
    judge = meta.get("judge") or {}
    record = {
        "run_id": run_dir.name,
        "started_at": meta["started_at"],
        "golden": meta["golden"]["name"],
        "golden_sha256": meta["golden"]["sha256"],
        "mode": meta["mode"],
        "limit": meta["golden"].get("limit") or "",
        "release_id": release.get("release_id") or "",
        "git_commit": release.get("git_commit") or "",
        "git_dirty": "" if release.get("git_dirty") is None else str(release.get("git_dirty")).lower(),
        "prompt_hash": release.get("prompt_hash") or "",
        "chat_model_id": release.get("chat_model_id") or "",
        "judge_model": judge.get("model") or "",
        "judge_prompt_hash": judge.get("prompt_hash") or "",
    }
    record.update({k: ("" if v is None else v) for k, v in scoring.aggregate(rows).items()})
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS, lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(record)


def load_run(run_dir: Path) -> tuple[list[dict], dict]:
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    return rows, meta


def find_previous(runs_dir: Path, meta: dict, exclude: Path) -> Path | None:
    """同じゴールデンセット名・方式・採点モデル・採点プロンプトの直近の実行（比較の基準）。"""
    candidates = []
    for run_dir in sorted(runs_dir.glob("*/meta.json")):
        if run_dir.parent == exclude:
            continue
        other = json.loads(run_dir.read_text(encoding="utf-8"))
        same = (
            (other.get("golden") or {}).get("name") == (meta.get("golden") or {}).get("name")
            and other.get("mode") == meta.get("mode")
            and other.get("judge") == meta.get("judge")
        )
        if same:
            candidates.append(run_dir.parent)
    return candidates[-1] if candidates else None


def summary_markdown(run_dir: Path, rows: list[dict], meta: dict, previous: Path | None) -> str:
    agg = scoring.aggregate(rows)
    release = meta.get("release") or {}
    judge = meta.get("judge")
    lines = [
        f"# 評価結果: {run_dir.name}",
        "",
        f"- ゴールデンセット: `{meta['golden']['path']}`（{meta['golden']['count']} 問, sha256 `{meta['golden']['sha256']}`）",
        f"- 方式: {meta['mode']}",
        f"- リリース: `{release.get('release_id') or '不明'}`（commit `{release.get('git_commit') or '不明'}`"
        f"{'・未コミット変更あり' if release.get('git_dirty') else ''}, prompt `{release.get('prompt_hash') or '不明'}`,"
        f" model `{release.get('chat_model_id') or '不明'}`）",
        f"- 採点: {('`' + judge['model'] + '`（effort ' + judge['effort'] + ', prompt `' + judge['prompt_hash'] + '`）') if judge else 'LLM 採点なし'}",
        f"- 実行: {meta['started_at']} 〜 {meta['finished_at']}（{meta['base_url']}）",
        "",
        "## 集計",
        "",
        "| 指標 | 値 |",
        "|---|---|",
    ]
    for key, label, _ in scoring.METRIC_LABELS:
        lines.append(f"| {label} | {agg.get(key)} |")
    problems = [r for r in rows if r.get("error") or r.get("judge_error")
                or (r["should_answer"] and (r["declined"] or (r.get("correctness") or 5) <= 2 or r.get("source_rank") == 0))
                or (not r["should_answer"] and not r["declined"])]
    if problems:
        lines += ["", "## 要確認の質問", "", "| ID | 質問 | 結果 | 理由 |", "|---|---|---|---|"]
        for r in problems:
            question = r["question"].replace("|", "｜").replace("\n", " ")[:50]
            reason = (r.get("error") or r.get("judge_error") or r.get("judge_reason") or "").replace("|", "｜").replace("\n", " ")[:100]
            if not r["should_answer"] and not r["declined"] and not r.get("error"):
                reason = "範囲外の質問に回答した。" + reason
            lines.append(f"| {r['id']} | {question} | {scoring._cell(r)} | {reason} |")
    if previous is not None:
        prev_rows, prev_meta = load_run(previous)
        lines += ["", scoring.compare_markdown(prev_rows, rows, previous.name, run_dir.name, prev_meta, meta)]
    else:
        lines += ["", "（同じ条件の前回実行が無いため、比較はありません）"]
    return "\n".join(lines) + "\n"


def run(base_url: str, golden_path: Path, mode: str, runs_dir: Path, repo: Path, judge=None,
        limit: int | None = None, ask=client_mod.ask, fetch_release=client_mod.fetch_release,
        now=now_jst, log=print, history_path: Path | None = None) -> Path:
    items = golden_mod.load(golden_path)
    if limit:
        items = items[:limit]
    qa_answers = golden_mod.load_qa_answers(repo)
    if qa_answers is None and judge is not None:
        log("注意: シード元データが無いため（dvc pull 前）、模範解答なしで採点します。")

    started = now()
    release = fetch_release(base_url)
    rows = []
    for i, item in enumerate(items, start=1):
        res = ask(base_url, mode, item["question"])
        row = {
            "id": item["id"],
            "question": item["question"],
            "category": item["category"],
            "should_answer": item["should_answer"],
            "expected_source_ids": item["expected_source_ids"],
            "mode": mode,
            "answer": res.get("answer"),
            "sources": res.get("sources"),
            "release_id": res.get("release_id"),
            "model": res.get("model"),
            "latency_ms": res.get("latency_ms"),
            "error": res.get("error"),
            "declined": scoring.is_declined(res.get("answer"), res.get("sources"), res.get("ask_mode") or mode),
            "source_rank": scoring.source_rank(item["expected_source_ids"], res.get("sources")),
            "correctness": None,
            "faithfulness": None,
            "judge_declined": None,
            "judge_reason": "",
            "judge_model": None,
            "judge_error": None,
        }
        if judge is not None and not row["error"]:
            row.update(judge.score(
                item["question"],
                item["should_answer"],
                golden_mod.reference_answer(item, qa_answers),
                res.get("context"),
                res.get("answer"),
            ))
            # 決定的な判定（定型の断り文言・出典なしの逆質問）は、出典を返さない古い agent_invitro では
            # 逆質問を検出できないため、LLM の判定と OR で合わせる。
            row["declined"] = row["declined"] or bool(row["judge_declined"])
        rows.append(row)
        log(f"[{i}/{len(items)}] {item['id']} {scoring._cell(row)}"
            + (f" ({row['error'] or row['judge_error']})" if row["error"] or row["judge_error"] else ""))

    release_id = (release or {}).get("release_id") or next((r["release_id"] for r in rows if r["release_id"]), None)
    run_dir = runs_dir / f"{started:%Y%m%d-%H%M%S}_{golden_path.stem}_{mode}"
    run_dir.mkdir(parents=True, exist_ok=False)
    meta = {
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "mode": mode,
        "golden": {"name": golden_path.stem, "path": f"evals/golden/{golden_path.name}",
                   "sha256": golden_mod.file_hash(golden_path), "count": len(items), "limit": limit},
        "release": release or ({"release_id": release_id} if release_id else None),
        "judge": judge.meta() if judge is not None else None,
        "reference_answers": "db_init/data（DVC）" if qa_answers is not None else None,
    }
    with (run_dir / "results.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    _write(run_dir / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    previous = find_previous(runs_dir, meta, exclude=run_dir)
    _write(run_dir / "summary.md", summary_markdown(run_dir, rows, meta, previous))
    append_history(history_path or runs_dir.parent / "history.csv", run_dir, rows, meta)
    return run_dir


def _write(path: Path, text: str) -> None:
    """LF で書く（Path.write_text の newline 引数は Python 3.10+ のため open を使う）。"""
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
