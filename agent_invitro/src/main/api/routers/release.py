"""GET /release（ADR-0099 §1）。

このプロセスが回答を生成している構成（リリース）の全要素を返す。admin_ui（web_backend）が
assistant メッセージの release_id を初めて見たときに呼び、conversation DB の release テーブルへ登録する。
MCP・Bedrock には触れない（load_settings のみ）ため、/ask-* より先に呼ばれても初期化を待たない。
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter

from ....config import load_settings
from ....release import build_release

router = APIRouter()


@lru_cache(maxsize=1)
def _release() -> dict:
    return build_release(load_settings())


@router.get("/release")
def release() -> dict:
    return _release()
