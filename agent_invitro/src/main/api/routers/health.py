"""GET /health（ECS コンテナヘルスチェック専用, ADR-0043 T2）。

プロセスが応答できることのみを 200 で返す。DB・MCP・Bedrock への到達性は確認しない
（既存 knowledge_mcp / tag_selector_mcp と同方針）。ALB 配下ではないため ALB ターゲット
グループのヘルスチェックとは別物。エンドポイントごとにヘルスチェックは分けない（ADR-0089 決定6）。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
