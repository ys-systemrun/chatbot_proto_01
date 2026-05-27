from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class QAOriginal:
    uuid: str
    question_text: str
    answer_text: str
    category_id: Optional[int] = None
