"""web_backend（stateless / admin_ui）の全ルート定義を集約する唯一のファイル。

旧構成（main/main_stateless.py にインラインのルート + main/admin_qa.py・main/admin_tags.py の
APIRouter）を 1 ファイルへ統合した。各ルートは薄く保ち、レスポンス生成の責務は
controllers/ 配下（chat/evaluation/qa/tag）に委譲する。

エントリポイント: src.main.app:app（pyproject [tool.fastapi] / Dockerfile CMD と一致）。
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi import Request as HttpRequest  # 下記スキーマの Request(BaseModel) と衝突するため別名
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from src.mcp_client import KnowledgeMcpError
from src.main import config
from src.main.controllers import (
    chat_controller,
    evaluation_controller,
    export_controller,
    qa_controller,
    tag_controller,
)

app = FastAPI()


@app.exception_handler(KnowledgeMcpError)
async def _knowledge_mcp_error_handler(_request: HttpRequest, exc: KnowledgeMcpError):
    """Knowledge MCP 側の業務エラー（QaError/TagError 相当）を 409 へマッピングする（T13）。"""
    return JSONResponse(status_code=409, content={"detail": exc.message})


# ---------------------------------------------------------------------------
# chat（stateless）: /api/ask-sl
# ---------------------------------------------------------------------------
# データAPIは SPA のページURL（/・/evaluated_messages・/admin*）と衝突しないよう、
# すべて /api/ 名前空間へ揃える。SPA フォールバック（catch-all）は /api/* を除外するため、
# ページURLは index.html、/api/* は本ルート群が処理する（ADR-0042/ADR-0015）。
@app.post("/api/ask-sl", response_model=chat_controller.Response)
def ask_sl(req: chat_controller.Request):
    return chat_controller.ask(req)


# ---------------------------------------------------------------------------
# 会話評価: /api/evaluate_response・/api/evaluated_messages
# ---------------------------------------------------------------------------
@app.post("/api/evaluate_response", response_model=evaluation_controller.EvaluateResponse)
def evaluate_response(req: evaluation_controller.EvaluateRequest):
    return evaluation_controller.evaluate_response(req)


@app.get(
    "/api/evaluated_messages",
    response_model=list[evaluation_controller.EvaluatedConversationOut],
)
def get_evaluated_messages():
    return evaluation_controller.get_evaluated_messages()


# ---------------------------------------------------------------------------
# 管理UI: /api/qa*・/api/categories
# ---------------------------------------------------------------------------
@app.get("/api/qa", response_model=qa_controller.QaListResponse)
async def list_qa(
    keyword: str | None = None,
    category: str | None = None,
    tag_id: list[int] | None = Query(default=None),
    limit: int = 20,
    offset: int = 0,
):
    return await qa_controller.list_qa(keyword, category, tag_id, limit, offset)


@app.get("/api/qa/{qa_id}", response_model=qa_controller.QaDetailResponse)
async def get_qa(qa_id: str):
    return await qa_controller.get_qa(qa_id)


@app.post("/api/qa", status_code=201, response_model=qa_controller.QaDetailResponse)
async def create_qa(body: qa_controller.QaCreateRequest):
    return await qa_controller.create_qa(body)


@app.put("/api/qa/{qa_id}", response_model=qa_controller.QaDetailResponse)
async def update_qa(qa_id: str, body: qa_controller.QaUpdateRequest):
    return await qa_controller.update_qa(qa_id, body)


@app.get("/api/categories", response_model=qa_controller.CategoryListResponse)
async def list_categories():
    return await qa_controller.list_categories()


# ---------------------------------------------------------------------------
# 管理UI: /api/tags*
# ---------------------------------------------------------------------------
@app.get("/api/tags", response_model=tag_controller.TagListResponse)
async def list_tags(parent_tag_id: int | None = None):
    return await tag_controller.list_tags(parent_tag_id)


@app.post("/api/tags", status_code=201)
async def create_tag(body: tag_controller.TagCreateRequest) -> dict:
    return await tag_controller.create_tag(body)


@app.put("/api/tags/{tag_id}")
async def update_tag(tag_id: int, body: tag_controller.TagUpdateRequest) -> dict:
    return await tag_controller.update_tag(tag_id, body)


@app.delete("/api/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: int) -> Response:
    await tag_controller.delete_tag(tag_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# 全データエクスポート: /api/export（ADR-0046/0047, IMPL-202608241600 T19）
# ---------------------------------------------------------------------------
# format は sql / csv のみ許可（pattern バリデーションにより sql/csv 以外は 422）。
# chatbot（読み取り専用ロール）・conversation 両データベースを読み、CSV は8ファイル・
# SQL は2ファイルを ZIP にまとめて application/zip + attachment で返す（5.5 節）。
@app.get("/api/export")
def export_data(format: str = Query(..., pattern="^(sql|csv)$")) -> Response:
    zip_bytes, filename = export_controller.build_export(format)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# /health（ALB ターゲットグループの HTTP ヘルスチェック専用, IMPL-202608211050 T1）
# ---------------------------------------------------------------------------
# ECS コンテナヘルスチェック（Docker HEALTHCHECK 相当）とは別物。DB や Knowledge MCP への
# 到達性は確認せず、プロセスが応答できることのみを 200 で返す（0章の決定）。
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 静的資産配信 + SPA フォールバック（IMPL-202608211050 T2/T3, ADR-0042/ADR-0015）
# ---------------------------------------------------------------------------
# front_dev の本番ビルド出力（npm run build の dist/）を AWS 用イメージ内の STATIC_DIR に
# 配置し、ルート直下から配信する。データAPI（/api/*）・/health・/docs 等の既存ルートは本ブロック
# より前に登録済みのため、それらに一致しない GET のみがフォールバックに到達する（T4: ルート順序）。
# 全データAPIを /api/ へ揃えたことで、SPA のページURL（/evaluated_messages 等）と衝突しない。
#
# STATIC_DIR が存在しない環境（ローカル docker-compose の web_backend。front は vite dev server が
# 別コンテナで配信）では本ブロックを一切登録しないため、既存の挙動に影響しない（ADR-0042）。
if config.STATIC_DIR.is_dir():
    _static_root = config.STATIC_DIR.resolve()
    _index_html = _static_root / "index.html"

    # ビルド成果物の実体（/assets/* 等）を効率よく返す。html=False によりディレクトリ index の
    # 自動フォールバックは行わず、未一致は下の catch-all（SPA フォールバック）へ委ねる。
    _assets_dir = _static_root / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        """/api・/health 等に一致しない GET は、実ファイルがあればそれを、無ければ index.html を返す。

        ブラウザのリロード・URL 直接入力（/admin 配下, react-router-dom, ADR-0015）でも
        SPA のエントリーポイントに到達できるようにする。パストラバーサルは静的ルート配下判定で防ぐ。
        """
        # API 名前空間・ヘルスチェックの未定義パスは SPA へ落とさず 404 のままにする（T3）。
        if full_path == "health" or full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        if full_path:
            candidate = (_static_root / full_path).resolve()
            if candidate.is_file() and (
                candidate == _static_root or _static_root in candidate.parents
            ):
                return FileResponse(candidate)
        return FileResponse(_index_html)
