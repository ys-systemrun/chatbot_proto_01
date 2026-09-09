"""トラブルシューティング記事の管理用データモデル（ADR-0079 / REQ-202609071337 9章）。

TroubleshootingSummary（一覧行）/ TroubleshootingDetail（詳細編集）と、業務エラー
TroubleshootingError を定義する。QA 管理（models/qa.py）と同様の構成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


class TroubleshootingError(Exception):
    """トラブルシューティング記事編集の業務エラー（対象不存在、存在しない tag_ids 指定等）。"""


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


@dataclass
class TroubleshootingSummary:
    id: int
    source_key: str
    title: str
    subtitle: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source_updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_key": self.source_key,
            "title": self.title,
            "subtitle": self.subtitle,
            "tags": list(self.tags),
            "source_updated_at": _iso(self.source_updated_at),
        }


@dataclass
class TroubleshootingDetail:
    id: int
    source_key: str
    title: str
    guidance: str
    subtitle: Optional[str] = None
    symptom: Optional[str] = None
    operation_history: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    system_environment: Optional[str] = None
    hardware_environment: Optional[str] = None
    version_info: Optional[str] = None
    cause: Optional[str] = None
    notes: Optional[str] = None
    keyword_raw: Optional[str] = None
    body_html: str = ""
    source_updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: List[dict] = field(default_factory=list)  # [{"id": int, "name": str}, ...]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_key": self.source_key,
            "title": self.title,
            "subtitle": self.subtitle,
            "symptom": self.symptom,
            "operation_history": self.operation_history,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "system_environment": self.system_environment,
            "hardware_environment": self.hardware_environment,
            "version_info": self.version_info,
            "guidance": self.guidance,
            "cause": self.cause,
            "notes": self.notes,
            "keyword_raw": self.keyword_raw,
            "body_html": self.body_html,
            "source_updated_at": _iso(self.source_updated_at),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "tags": list(self.tags),
        }
