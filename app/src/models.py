from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class QaOriginal:
    uuid: str
    question_text: str
    answer_text: str
    category_id: Optional[int] = None


@dataclass
class Category:
    id: int
    name: str


@dataclass
class QuestionAltered:
    qa_id: str
    text: str
    embedding: Optional[List[float]] = None
    id: Optional[int] = None

    def to_tuple(self):
        if self.id is None:
            return (self.qa_id, self.text, self.embedding)
        return (self.id, self.qa_id, self.text, self.embedding)
