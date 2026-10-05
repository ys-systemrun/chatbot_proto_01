"""agent_invitro への中継（ADR-0045 / ADR-0089 決定5）。

`chat_controller`（LM Studio を使うローカル直接処理）とは別のコントローラとして独立させ、
ルート定義の時点でどちらの実装に入るかが決まるようにしている。実行時に環境変数の有無で
経路を選ぶ分岐は持たない。

- `ask_pipeline()` … agent_invitro の `POST /ask-pipeline`（単発プロンプト生成方式, ADR-0043）へ中継
- `ask_agentic()`  … agent_invitro の `POST /ask-agentic`（Agentic 探索ループ, ADR-0088）へ中継

リクエスト・レスポンスのスキーマは両者で完全に同一で、中継先パスだけが異なる。
本モジュールは LLM 呼び出し・`knowledge` データベースへのクエリを一切行わない（ADR-0045 決定1）。
"""

import httpx
from fastapi import HTTPException

from src.main import config
from src.main.controllers.chat_schemas import Request, Response

# agent_invitro 側のパス。front_dev の回答生成方式トグルが、web_backend のどちらのルートを
# 叩くかによって決まる（ADR-0089 決定5）。
ASK_PIPELINE_PATH = "/ask-pipeline"
ASK_AGENTIC_PATH = "/ask-agentic"


def ask_pipeline(req: Request) -> Response:
    """パイプライン方式（ADR-0043）。"""
    return _relay(req, ASK_PIPELINE_PATH)


def ask_agentic(req: Request) -> Response:
    """エージェント方式（ADR-0088）。"""
    return _relay(req, ASK_AGENTIC_PATH)


def _relay(req: Request, path: str) -> Response:
    """リクエストをそのまま agent_invitro へ中継し、レスポンスをそのまま返す。"""
    url = f"{config.AGENT_INVITRO_BASE_URL}{path}"
    try:
        resp = httpx.post(
            url,
            json=req.model_dump(),
            timeout=config.AGENT_INVITRO_TIMEOUT,
        )
    except httpx.RequestError as exc:
        # 接続不可・タイムアウト等（agent_invitro 未起動/到達不可）。502 で明示する。
        raise HTTPException(
            status_code=502,
            detail=f"agent_invitro ({url}) への接続に失敗しました: {exc}",
        )
    # agent_invitro 側のエラー（500 等）を bare 500 で握りつぶさず、ステータスと
    # detail（{"detail": ...} 形式想定）をそのまま透過してブラウザ/ログに原因を残す。
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return Response(**resp.json())
