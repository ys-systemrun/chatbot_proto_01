"""POST /ask-agentic（ADR-0088 / ADR-0089 / ADR-0090 決定3）。

`/ask-pipeline` と完全に同一のリクエスト・レスポンススキーマを持つ（ADR-0089 決定2）。
実処理は usecases/ask_agentic.py にある。本モジュールは契約の宣言と例外変換のみを担う。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ....usecases.ask_agentic import ask_agentic
from ..dependencies import get_components
from ..schemas import Request, Response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ask-agentic", response_model=Response)
async def ask(req: Request) -> Response:
    """例外方針は /ask-pipeline と同一（F-6.1.5）。Agentic ループの追加要素（十分性評価・
    逆質問生成）が失敗しても、それ自体は各モジュール内で縮退するため 500 にはならない
    （F-6.3.8 / F-6.5.3 / N-8.3）。"""
    try:
        return await ask_agentic(req, await get_components())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 予期しない例外は詳細をログ+レスポンスへ伝える
        logger.exception("POST /ask-agentic failed")
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")
