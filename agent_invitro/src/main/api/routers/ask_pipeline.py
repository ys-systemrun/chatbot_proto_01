"""POST /ask-pipeline（ADR-0043 T3 / ADR-0090 決定3）。

実処理は usecases/ask_pipeline.py にある。本モジュールは契約の宣言と例外変換のみを担う。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ....usecases.ask_pipeline import ask_pipeline
from ..dependencies import get_components
from ..schemas import Request, Response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ask-pipeline", response_model=Response)
async def ask(req: Request) -> Response:
    """例外を握りつぶさず、スタックトレースをログ出力したうえでエラー種別・メッセージを
    500 の detail に含めて返す（社内IP限定のため詳細開示は許容, ADR-0090 決定3）。"""
    try:
        return await ask_pipeline(req, await get_components())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 予期しない例外は詳細をログ+レスポンスへ伝える
        logger.exception("POST /ask-pipeline failed")
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")
