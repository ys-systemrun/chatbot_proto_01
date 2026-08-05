"""Document データモデル（実装指示書 5.1 / 要件6.2）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Document:
    id: str
    source_type: str        # "qa" 固定（MVP時点）
    title: str
    content: str
    score: float            # 0.0〜1.0
    metadata: dict = field(default_factory=dict)  # {"tags": list[str], "category": str, "guid": str}

    def to_dict(self) -> dict:
        """MCP出力スキーマ（5.5節）に沿った辞書へ変換する。"""
        return {
            "id": self.id,
            "source_type": self.source_type,
            "title": self.title,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }
