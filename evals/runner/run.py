"""ゴールデンセット評価の実行（ADR-0099 §5 `run` / `compare`、ADR-0101 `judge`）。

結果は `evals/runs/<日時>_<ゴールデンセット>_<方式>/` に保存する。質問・回答・参考情報を含むため
git には入れず DVC で管理する（`evals/runs.dvc`）。
  - results.jsonl : 1問1行（質問・回答・出典・回答時の参考情報・各スコア・採点理由・release_id）
  - meta.json     : リリースの全要素・ゴールデンセットの版・採点側の版・費用の概算に使った単価表
  - summary.md    : 集計・採点のトークン数と概算費用（ADR-0100）と、同じ条件の前回実行との比較
あわせて、数値だけの1行を `evals/history.csv`（git 管理）に追記し、git の差分で推移を追えるようにする。

回答の収集と採点は分けて行う（ADR-0101 §4）。`run` は収集に続けて採点し、`rejudge` は保存済みの回答を
採点し直す（使用量の上限で止まった残りの採点、採点方式・採点プロンプトを変えたときの再採点）。
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import client as client_mod
from . import golden as golden_mod
from . import scoring
from .judge import JudgeAbort

MODES = ("pipeline", "agentic")

# 実行日時は日本時間で記録する（コンテナの時計は UTC のため）。
JST = timezone(timedelta(hours=9), "JST")


def now_jst() -> datetime:
    return datetime.now(JST)

# evals/history.csv の列（質問・回答などの文は含めない。数値と版だけ）。
HISTORY_COLUMNS = [
    "run_id", "started_at", "golden", "golden_sha256", "mode", "limit",
    "release_id", "git_commit", "git_dirty", "prompt_hash", "chat_model_id",
    "judge_model", "judge_prompt_hash", "judge_backend",
] + [key for key, _, _ in scoring.METRIC_LABELS] + [key for key, _ in scoring.USAGE_LABELS]

# 採点で埋まる列（未採点の初期値。再採点の前にもこの値に戻す）。
JUDGE_FIELDS = {
    "correctness": None,
    "faithfulness": None,
    "judge_declined": None,
    "judge_reason": "",
    "judge_model": None,
    "judge_error": None,
    "judge_calls": None,
    "judge_input_tokens": None,
    "judge_output_tokens": None,
    "judge_thinking_tokens": None,
    "judge_cache_write_tokens": None,
    "judge_cache_read_tokens": None,
    "judge_cost_usd": None,
}


def append_history(path: Path, run_dir: Path, rows: list[dict], meta: dict, replace: bool = False) -> None:
    """1回の実行を1行として evals/history.csv に追記する（無ければヘッダーから作る）。
    replace=True なら同じ run_id の行を置き換える（採点の続きを同じ実行に書き足したとき）。"""
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
        "judge_backend": (judge.get("backend") or "bedrock") if judge else "",
    }
    record.update({k: ("" if v is None else v) for k, v in scoring.aggregate(rows).items()})
    record.update({k: ("" if v is None else v) for k, v in scoring.judge_usage(rows).items()})
    _upgrade_history_header(path)
    if replace and path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            kept = [r for r in csv.DictReader(f) if r["run_id"] != record["run_id"]]
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(kept + [record])
        return
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS, lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(record)


def _upgrade_history_header(path: Path) -> None:
    """列が増えた後の初回追記で、既存の history.csv を新しい列構成に書き直す（既存行の新しい列は空欄）。"""
    if not path.exists():
        return
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == HISTORY_COLUMNS:
            return
        old = list(reader)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(old)


def load_run(run_dir: Path) -> tuple[list[dict], dict]:
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    return rows, meta


def judge_key(meta: dict) -> dict | None:
    """前回比較の条件にする採点の版。採点方式（backend）を含め、CLI の版は含めない。
    backend の記録が無い実行（ADR-0101 より前）は Bedrock で採点したものとして扱う。"""
    judge = meta.get("judge")
    if not judge:
        return None
    key = {k: v for k, v in judge.items() if k != "cli_version"}
    key.setdefault("backend", "bedrock")
    return key


def find_previous(runs_dir: Path, meta: dict, exclude: Path) -> Path | None:
    """同じゴールデンセット名・方式・採点モデル・採点プロンプト・採点方式の直近の実行（比較の基準）。"""
    candidates = []
    for run_dir in sorted(runs_dir.glob("*/meta.json")):
        if run_dir.parent == exclude:
            continue
        other = json.loads(run_dir.read_text(encoding="utf-8"))
        same = (
            (other.get("golden") or {}).get("name") == (meta.get("golden") or {}).get("name")
            and other.get("mode") == meta.get("mode")
            and judge_key(other) == judge_key(meta)
        )
        if same:
            candidates.append(run_dir.parent)
    return candidates[-1] if candidates else None


def _judge_line(judge: dict | None) -> str:
    if not judge:
        return "LLM 採点なし"
    backend = judge.get("backend") or "bedrock"
    via = "Claude Code（`claude -p`、サブスクリプション）" if backend == "claude-code" else "Amazon Bedrock"
    version = f", CLI {judge['cli_version']}" if judge.get("cli_version") else ""
    return (f"`{judge['model']}`（{via}, effort {judge['effort']}, prompt `{judge['prompt_hash']}`{version}）")


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
        f"- 採点: {_judge_line(judge)}",
        f"- 実行: {meta['started_at']} 〜 {meta['finished_at']}（{meta['base_url']}）",
    ]
    if meta.get("answers_from"):
        lines.append(f"- 回答: `{meta['answers_from']}` の回答を採点し直したもの（{meta.get('judged_at')}）")
    incomplete = meta.get("judge_incomplete")
    if incomplete:
        lines += ["", f"> **採点が途中で止まりました**（{incomplete['reason']}）。未採点 {incomplete['unjudged']} 問。"
                      f"原因を解消してから（使用量の上限ならリセット後に）"
                      f"`evals\\eval.bat judge {run_dir.name} --only-missing` で残りを採点してください。"]
    lines += [
        "",
        "## 集計",
        "",
        "| 指標 | 値 |",
        "|---|---|",
    ]
    for key, label, _ in scoring.METRIC_LABELS:
        lines.append(f"| {label} | {agg.get(key)} |")
    if judge:
        usage = scoring.judge_usage(rows)
        prices = meta.get("judge_prices") or {}
        lines += ["", "## 採点のトークン数と概算費用", "", "| 項目 | 値 |", "|---|---|"]
        lines += [f"| {label} | {usage.get(key)} |" for key, label in scoring.USAGE_LABELS]
        note = ""
        if judge.get("backend") == "claude-code":
            note = "Claude Code（サブスクリプション）で採点したため、費用は API 単価換算の値で、実際の請求額ではない。"
        lines += ["", f"単価: `evals/judge_prices.json`（{prices.get('source') or '単価表なし'}）。{note}"
                      "回答側（Amazon Nova・Titan Embeddings）の費用は含まない。"]
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


def judge_rows(rows: list[dict], items_by_id: dict[str, dict], judge, qa_answers, log=print,
               only_missing: bool = False) -> dict | None:
    """回答済みの行を採点して書き換える。回答側がエラーの行は採点しない。
    使用量の上限・認証の失敗で以降も採点できないときは、残りを「採点不可」で埋めずに止め、
    {"reason", "unjudged"} を返す（最後まで採点できたら None）。"""
    targets = [r for r in rows if not r.get("error") and not (only_missing and r.get("judge_calls") is not None)]
    for i, row in enumerate(targets, start=1):
        try:
            result = judge.score(
                row["question"],
                row["should_answer"],
                golden_mod.reference_answer(items_by_id[row["id"]], qa_answers),
                row.get("context"),
                row.get("answer"),
            )
        except JudgeAbort as exc:
            unjudged = len(targets) - i + 1
            log(f"{exc.label}のため、採点を止めます（未採点 {unjudged} 問）: {exc}")
            return {"reason": f"{exc.label}: {str(exc)[:200]}", "unjudged": unjudged}
        row.update(result)
        # 決定的な判定（定型の断り文言・出典なしの逆質問）は、出典を返さない古い agent_invitro では
        # 逆質問を検出できないため、LLM の判定と OR で合わせる。
        row["declined"] = scoring.is_declined(row.get("answer"), row.get("sources"), row["mode"]) \
            or bool(row["judge_declined"])
        log(f"[採点 {i}/{len(targets)}] {row['id']} {scoring._cell(row)}"
            + (f" ({row['judge_error']})" if row["judge_error"] else ""))
    return None


def _save(run_dir: Path, rows: list[dict], meta: dict, runs_dir: Path, history_path: Path | None,
          replace_history: bool = False) -> None:
    with (run_dir / "results.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    _write(run_dir / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    previous = find_previous(runs_dir, meta, exclude=run_dir)
    _write(run_dir / "summary.md", summary_markdown(run_dir, rows, meta, previous))
    append_history(history_path or runs_dir.parent / "history.csv", run_dir, rows, meta, replace=replace_history)


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
            # 回答時の参考情報。採点だけを後からやり直すために保存する（ADR-0101 §4）。
            "context": res.get("context"),
            "release_id": res.get("release_id"),
            "model": res.get("model"),
            "latency_ms": res.get("latency_ms"),
            "error": res.get("error"),
            "declined": scoring.is_declined(res.get("answer"), res.get("sources"), res.get("ask_mode") or mode),
            "source_rank": scoring.source_rank(item["expected_source_ids"], res.get("sources")),
            **JUDGE_FIELDS,
        }
        rows.append(row)
        log(f"[{i}/{len(items)}] {item['id']} {scoring._cell(row)}" + (f" ({row['error']})" if row["error"] else ""))

    stopped = None
    if judge is not None:
        stopped = judge_rows(rows, {item["id"]: item for item in items}, judge, qa_answers, log=log)

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
        # 単価は比較条件（judge）に入れない。単価を書き換えるたびに前回実行との比較が途切れるため。
        "judge_prices": getattr(judge, "prices", None) if judge is not None else None,
        "judge_incomplete": stopped,
        "reference_answers": "db_init/data（DVC）" if qa_answers is not None else None,
    }
    _save(run_dir, rows, meta, runs_dir, history_path)
    return run_dir


def rejudge(source_dir: Path, judge, runs_dir: Path, repo: Path, only_missing: bool = False,
            now=now_jst, log=print, history_path: Path | None = None) -> Path:
    """保存済みの回答を採点する（ADR-0101 §4）。
    - only_missing=True: 未採点の質問だけを同じ実行に書き足す（使用量の上限で止まった続き）。採点条件が同じこと。
    - only_missing=False: 全問を採点し直し、新しい実行ディレクトリに保存する（元の実行は残す）。"""
    rows, meta = load_run(source_dir)
    missing_context = [r["id"] for r in rows if not r.get("error") and "context" not in r]
    if missing_context:
        raise ValueError(f"{source_dir.name} は回答時の参考情報（context）を保存していないため、採点し直せません"
                         f"（ADR-0101 より前の実行）: {', '.join(missing_context[:5])}")
    golden_path = repo / meta["golden"]["path"]
    if not golden_path.exists() or golden_mod.file_hash(golden_path) != meta["golden"]["sha256"]:
        raise ValueError(f"{meta['golden']['path']} が実行時と異なるため、同じ模範解答で採点できません")
    items_by_id = {item["id"]: item for item in golden_mod.load(golden_path)}
    qa_answers = golden_mod.load_qa_answers(repo)
    if qa_answers is None:
        log("注意: シード元データが無いため（dvc pull 前）、模範解答なしで採点します。")

    if only_missing:
        if meta.get("judge") and judge_key(meta) != judge_key({"judge": judge.meta()}):
            raise ValueError("元の実行と採点条件（モデル・プロンプト・方式）が異なるため、続きとして採点できません。"
                             "--only-missing を外すと、新しい実行として全問を採点し直せます。")
        stopped = judge_rows(rows, items_by_id, judge, qa_answers, log=log, only_missing=True)
        meta.update({"judge": meta.get("judge") or judge.meta(), "judge_incomplete": stopped,
                     "judge_prices": meta.get("judge_prices") or judge.prices})
        _save(source_dir, rows, meta, runs_dir, history_path, replace_history=True)
        return source_dir

    for row in rows:
        row.update(JUDGE_FIELDS)
    stopped = judge_rows(rows, items_by_id, judge, qa_answers, log=log)
    judged_at = now()
    run_dir = runs_dir / f"{judged_at:%Y%m%d-%H%M%S}_{meta['golden']['name']}_{meta['mode']}"
    run_dir.mkdir(parents=True, exist_ok=False)
    meta = {**meta, "judge": judge.meta(), "judge_prices": judge.prices, "judge_incomplete": stopped,
            "answers_from": source_dir.name, "judged_at": judged_at.isoformat(timespec="seconds")}
    _save(run_dir, rows, meta, runs_dir, history_path)
    return run_dir


def _write(path: Path, text: str) -> None:
    """LF で書く（Path.write_text の newline 引数は Python 3.10+ のため open を使う）。"""
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
