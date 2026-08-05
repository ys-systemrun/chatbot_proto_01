"""チャットセッションのログをファイルに書き出すモジュール。

ファイルシステムへの I/O 処理はすべてこのモジュールに集約する。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent / "logs"


def open_log_file() -> Path:
    """ログディレクトリを作成し、日時付きのログファイルを生成してそのパスを返す。

    ファイル名形式: chat_YYYYMMDD_HHMMSS.log
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = _LOG_DIR / f"chat_{timestamp}.log"
    log_path.touch()
    return log_path


def write_session_start(log_path: Path, strategy_name: str) -> None:
    """セッション開始情報をログファイルに書き出す。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{'#'*60}\n")
        f.write(f"# チャットセッション開始: {timestamp}\n")
        f.write(f"# 適合判定ストラテジー: {strategy_name}\n")
        f.write(f"{'#'*60}\n\n")


def write_turn(
    log_path: Path,
    turn: int,
    user_input: str,
    search_results: list[tuple],
    answer: str,
    state_dicts: list[dict[str, str]],
) -> None:
    """1 ターン分の情報（ユーザー入力・検索結果・回答・会話状態）をログファイルに追記する。

    Args:
        log_path: 書き込み先ログファイルのパス。
        turn: 現在のターン番号（1 始まり）。
        user_input: ユーザーの入力テキスト。
        search_results: DB の search_similar が返したタプルのリスト。
            各タプルは (q_similar, answer, q_original, qa_id, distance)。
        answer: LLM が生成した回答テキスト。
        state_dicts: ConversationState.messages_as_dicts() の戻り値。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{'='*60}\n")
        f.write(f"[Turn {turn}]  {timestamp}\n")
        f.write(f"{'='*60}\n\n")

        # ユーザー入力
        f.write("[ユーザー入力]\n")
        f.write(f"{user_input}\n\n")

        # search_similar の結果
        f.write("[search_similar 結果]\n")
        if search_results:
            for i, r in enumerate(search_results, 1):
                q_similar, a_original, q_original, qa_id, distance = r
                f.write(f"  [{i}]\n")
                f.write(f"    Q_similar  : {q_similar}\n")
                f.write(f"    Q_original : {q_original}\n")
                f.write(f"    A_original : {a_original}\n")
                f.write(f"    qa_id      : {qa_id}\n")
                f.write(f"    距離        : {distance:.6f}\n")
        else:
            f.write("  (結果なし)\n")
        f.write("\n")

        # LLM の回答
        f.write("[アシスタント回答]\n")
        f.write(f"{answer}\n\n")

        # ConversationState の全履歴
        f.write("[ConversationState]\n")
        f.write(json.dumps(state_dicts, ensure_ascii=False, indent=2))
        f.write("\n\n")
