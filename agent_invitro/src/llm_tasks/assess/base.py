"""十分性評価の抽象基底クラス（ADR-0091 決定3）。

プロバイダ差し替えの境界を型として固定する。`graph/agentic_search.py`・`usecases/ask_agentic.py`
はこの抽象にのみ依存し、具象クラス名を持たない（ADR-0091 決定4）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# 評価に失敗した場合の縮退値（F-6.3.8）。実装はこれを返してループを抜けさせる。
DEGRADED_ASSESSMENT: dict = {"sufficient": True, "missing": "", "next_query": ""}


class SufficiencyAssessor(ABC):
    """「これまでの検索結果で質問に回答できるか」を判定する評価器のインターフェース。

    実装・テストスタブの双方が従う契約（ADR-0091 決定3）:

    - **同期メソッドである。** 想定する実装（boto3 等）が同期APIであるため非同期化しない。
      呼び出し側が `anyio.to_thread` でスレッドプールへ逃がす。
    - **例外を送出しない。** LLM呼び出しの失敗・出力のパース失敗はすべて実装内で捕捉し、
      `DEGRADED_ASSESSMENT` を返して探索ループを抜けさせる（F-6.3.8）。失敗は実装側で
      ログに残す（F-6.6.2）。探索ループの制御フローがこの性質に依存している。
    - **戻り値は `{"sufficient": bool, "missing": str, "next_query": str}` の3キーを必ず含む。**
      `sufficient` が True のとき `missing`・`next_query` は空文字列とする。
    - **プロンプトの構築と出力のパースは実装の責務。** プロバイダごとに最適なプロンプト・
      出力制約手段が異なるため、インターフェースはプロンプト形式を含めない。
    """

    @abstractmethod
    def assess(
        self, question: str, results: list[dict], tried_queries: list[str]
    ) -> dict:
        """十分性を評価し `{"sufficient", "missing", "next_query"}` を返す。

        Args:
            question: ユーザーの質問（言い換え後のクエリ, ADR-0085）。
            results: これまでに蓄積した検索結果（重複排除済み, F-6.3.7）。
            tried_queries: すでに試した検索クエリ（同一クエリの再試行抑止, F-6.3.6）。
        """
        raise NotImplementedError
