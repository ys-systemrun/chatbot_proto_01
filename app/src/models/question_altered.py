from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


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
