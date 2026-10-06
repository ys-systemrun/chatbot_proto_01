"""検索結果の十分性評価（ADR-0088 決定2 / ADR-0091 / F-6.3.2）。

呼び出し側はこのパッケージの公開APIのみを参照し、`bedrock`・`parsing` 等の下位モジュールを
直接importしない（テストが純関数を直接importする場合を除く, ADR-0091 決定2）。
"""

from .base import SufficiencyAssessor
from .bedrock import SufficiencyAssessorBedrock
from .parsing import parse_assessment
# リリースの prompt_hash 算出用に公開する（ADR-0099 §1）。
from .prompts import SYSTEM_PROMPT as ASSESS_SYSTEM_PROMPT

__all__ = [
    "SufficiencyAssessor",
    "SufficiencyAssessorBedrock",
    "parse_assessment",
    "ASSESS_SYSTEM_PROMPT",
]
