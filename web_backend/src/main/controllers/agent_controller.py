"""agent_invitro への中継（ADR-0045 / ADR-0089 決定5）。

`chat_controller`（LM Studio を使うローカル直接処理）とは別のコントローラとして独立させ、
ルート定義の時点でどちらの実装に入るかが決まるようにしている。実行時に環境変数の有無で
経路を選ぶ分岐は持たない。

- `ask_pipeline()` … agent_invitro の `POST /ask-pipeline`（単発プロンプト生成方式, ADR-0043）へ中継
- `ask_agentic()`  … agent_invitro の `POST /ask-agentic`（Agentic 探索ループ, ADR-0088）へ中継

リクエスト・レスポンスのスキーマは両者で完全に同一で、中継先パスだけが異なる。
本モジュールは LLM 呼び出し・`knowledge` データベースへのクエリを一切行わない（ADR-0045 決定1）。
conversation データベースへは、回答に付いたリリースの登録（ADR-0099 §1）だけを行う。
"""

import logging

import httpx
from fastapi import HTTPException

from src.conversation_db import ConversationDB
from src.main import config
from src.main.controllers.chat_schemas import Request, Response

logger = logging.getLogger(__name__)

# agent_invitro 側のパス。front_dev の回答生成方式トグルが、web_backend のどちらのルートを
# 叩くかによって決まる（ADR-0089 決定5）。
ASK_PIPELINE_PATH = "/ask-pipeline"
ASK_AGENTIC_PATH = "/ask-agentic"
RELEASE_PATH = "/release"  # ADR-0099 §1


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
    response = Response(**resp.json())
    _ensure_releases_registered(response)
    return response


def get_release() -> dict:
    """agent_invitro の GET /release をそのまま返す（ADR-0099 §1）。"""
    url = f"{config.AGENT_INVITRO_BASE_URL}{RELEASE_PATH}"
    try:
        resp = httpx.get(url, timeout=10)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"agent_invitro ({url}) への接続に失敗しました: {exc}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# 登録済み（または登録を試みた）release_id。プロセス内キャッシュで、毎回の DB 照会を避ける。
_known_release_ids: set[str] = set()


def _ensure_releases_registered(response: Response) -> None:
    """回答に付いた release_id を conversation DB の release テーブルへ登録する（ADR-0099 §1）。

    回答を返した直後に agent_invitro の GET /release を呼ぶので、取得した内容は確実にこの回答を
    生成した構成と一致する（評価時まで待つと、その間の再デプロイで別の構成を取りうる）。
    登録はベストエフォートで、失敗してもチャット応答は妨げない（失敗した ID は次回に再試行する）。
    """
    release_ids = {
        m.release_id for m in response.messages if m.role == "assistant" and m.release_id
    } - _known_release_ids
    for release_id in release_ids:
        try:
            with ConversationDB(config.CONVERSATION_DB_URL) as db:
                if not db.has_release(release_id):
                    release = httpx.get(
                        f"{config.AGENT_INVITRO_BASE_URL}{RELEASE_PATH}", timeout=10
                    ).raise_for_status().json()
                    if release.get("release_id") != release_id:
                        logger.warning(
                            "agent_invitro の現在のリリース（%s）が回答の release_id（%s）と異なるため登録しません",
                            release.get("release_id"),
                            release_id,
                        )
                        continue
                    db.register_release(release)
            _known_release_ids.add(release_id)
        except Exception:  # noqa: BLE001 - 登録失敗でチャット応答を落とさない
            logger.exception("release %s の登録に失敗しました", release_id)
