"""FastAPI アプリの組み立て（ADR-0090 決定1 / F-6.7.1）。

`create_app()` で FastAPI インスタンスを生成し、ルーターを登録してロギングを設定する。
起動エントリポイント（server.py）はこの関数を呼ぶだけの薄いモジュールに保つ。

提供するエンドポイント（ADR-0089 結果・影響）:
- GET  /health       : プロセス生存確認のみ（DB・MCP への到達性チェックは行わない, ADR-0043 T2）
- POST /ask-pipeline : 単発プロンプト生成方式（ADR-0043 0章）
- POST /ask-agentic  : Agentic 探索ループ方式（ADR-0088）。契約は /ask-pipeline と同一

本アプリは conversation データベースへ一切アクセスしない（ADR-0043 / T8）。評価機能は
admin_ui 側の責務であり、ここでは会話生成のみを担う。既存の main/ipython/main.py（IPython 用
エントリポイント）とは独立しており、import 時の副作用（load_settings 等）を持たない（T9）。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .routers import ask_agentic, ask_pipeline, health, release


def create_app() -> FastAPI:
    # INFO/ERROR ログを CloudWatch（stdout/stderr）へ確実に流す。uvicorn の既定設定は本パッケージの
    # ロガーを構成しないため、明示的に basicConfig する（未構成時のみ有効）。
    logging.basicConfig(level=logging.INFO)

    app = FastAPI()
    app.include_router(health.router)
    app.include_router(release.router)
    app.include_router(ask_pipeline.router)
    app.include_router(ask_agentic.router)
    return app
