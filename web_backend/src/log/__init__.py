"""日付ごとの JSONL ファイルにログを書き出すモジュール。"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(os.environ.get("LOG_DIR", "logs"))


def _write(entry: dict) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        with (_LOG_DIR / f"{date_str}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, indent="\t") + "\n")
    except Exception as e:
        print(f"[log] write error: {e}", flush=True)


def log_search(question: str, results: list, model: str) -> None:
    """類似検索の入力と結果を記録する。"""
    _write({
        "timestamp": datetime.now().isoformat(),
        "type": "search",
        "model": model,
        "question": question,
        "results": [
            {"q_similar": r[0], "a_original": r[1], "q_original": r[2]}
            for r in results
        ],
    })


def log_format_query(input_content: str, formatted_query: str, model: str) -> None:
    """FormatQueryToEmbed の入力と生成されたクエリを記録する。"""
    _write({
        "timestamp": datetime.now().isoformat(),
        "type": "format_query",
        "model": model,
        "input": input_content,
        "formatted_query": formatted_query,
    })


def log_generate(prompt: str, answer: str, model: str) -> None:
    """LLM へのプロンプトと得られた回答を記録する。"""
    _write({
        "timestamp": datetime.now().isoformat(),
        "type": "generate",
        "model": model,
        "prompt": prompt,
        "answer": answer,
    })


def log_admin_operation(
    operation: str,
    target: str,
    target_id,
    changes: dict | None = None,
) -> None:
    """管理UIの書き込み操作を記録する（IMPL-202608060837 0節）。

    認証方式未確定のため操作者は記録せず、操作種別（作成/更新/削除）・対象種別・
    対象ID・変更内容・タイムスタンプのみを記録する。
    """
    _write({
        "timestamp": datetime.now().isoformat(),
        "type": "admin_operation",
        "operation": operation,   # "create" | "update" | "delete"
        "target": target,         # "qa" | "tag"
        "target_id": target_id,
        "changes": changes or {},
    })
