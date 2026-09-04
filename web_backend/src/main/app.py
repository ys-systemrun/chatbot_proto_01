"""web_backend（stateless / admin_ui）の全ルート定義を集約する唯一のファイル。

旧構成（main/main_stateless.py にインラインのルート + main/admin_qa.py・main/admin_tags.py の
APIRouter）を 1 ファイルへ統合した。各ルートは薄く保ち、レスポンス生成の責務は
controllers/ 配下（chat/evaluation/qa/tag）に委譲する。

エントリポイント: src.main.app:app（pyproject [tool.fastapi] / Dockerfile CMD と一致）。
"""

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
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
    question_altered_controller,
    tag_controller,
    verification_controller,
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


# QA の削除（ADR-0067）。紐づく qa_tag・question_altered（主質問文行・言い換え行）を
# カスケード削除する。存在しない QA は Knowledge MCP の QaError → 409（グローバルハンドラ）。
@app.delete("/api/qa/{qa_id}", status_code=204)
async def delete_qa(qa_id: str) -> Response:
    await qa_controller.delete_qa(qa_id)
    return Response(status_code=204)


# QA の CSV 一括インポート（IMPL-202608261022 T11 / ADR-0053）。存在しないタグ名は自動作成する。
# multipart/form-data の file を受け取り、Knowledge MCP の import_qa_batch へ委ねる。
@app.post("/api/qa/import", response_model=qa_controller.QaImportResponse)
async def import_qa(file: UploadFile = File(...)):
    return await qa_controller.import_qa_csv(await file.read())


@app.get("/api/categories", response_model=qa_controller.CategoryListResponse)
async def list_categories():
    return await qa_controller.list_categories()


# ---------------------------------------------------------------------------
# 管理UI: /api/hiroba_question_altered*（言い換え行管理, ADR-0064）
# ---------------------------------------------------------------------------
# is_primary=false の言い換え行のみを対象とする。/export・/import は /{item_id}（int）より
# 前に登録し、パスパラメータへ誤って一致しないようにする（T4 / 検証機能と同じ配慮）。
@app.get(
    "/api/hiroba_question_altered",
    response_model=question_altered_controller.QaAlteredListResponse,
)
async def list_question_altered(
    qa_id: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    return await question_altered_controller.list_items(qa_id, keyword, limit, offset)


# CSVエクスポート（is_primary=false 全件）。text/csv + attachment で返す。
@app.get("/api/hiroba_question_altered/export")
async def export_question_altered() -> Response:
    csv_bytes, filename = await question_altered_controller.build_export_csv()
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# CSV一括インポート（id によるupsert、is_primary=true 行はエラー、行単位で部分成功）。
@app.post(
    "/api/hiroba_question_altered/import",
    response_model=question_altered_controller.QaAlteredImportResponse,
)
async def import_question_altered(file: UploadFile = File(...)):
    return await question_altered_controller.import_csv(await file.read())


@app.get(
    "/api/hiroba_question_altered/{item_id}",
    response_model=question_altered_controller.QaAlteredDetail,
)
async def get_question_altered(item_id: int):
    return await question_altered_controller.get_item(item_id)


@app.post(
    "/api/hiroba_question_altered",
    status_code=201,
    response_model=question_altered_controller.QaAlteredDetail,
)
async def create_question_altered(
    body: question_altered_controller.QaAlteredCreateRequest,
):
    return await question_altered_controller.create_item(body)


@app.put(
    "/api/hiroba_question_altered/{item_id}",
    response_model=question_altered_controller.QaAlteredDetail,
)
async def update_question_altered(
    item_id: int, body: question_altered_controller.QaAlteredUpdateRequest
):
    return await question_altered_controller.update_item(item_id, body)


@app.delete("/api/hiroba_question_altered/{item_id}", status_code=204)
async def delete_question_altered(item_id: int) -> Response:
    await question_altered_controller.delete_item(item_id)
    return Response(status_code=204)


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


# タグを兄弟集合内で1つ上／下へ並べ替える（ADR-0074）。body: {"direction": "up" | "down"}。
# 先頭で up／末尾で down は No-Op（Knowledge MCP 側で更新なし）。表示順序のみ変更し検索には影響しない。
@app.patch("/api/tags/{tag_id}/reorder")
async def reorder_tag(
    tag_id: int, body: tag_controller.TagReorderRequest
) -> dict:
    return await tag_controller.reorder_tag(tag_id, body)


# タグの CSV エクスポート（IMPL-202608281500 / ADR-0065）。全タグを name/parent_name/description の
# 3列（import_tag_batch と完全一致、そのまま再インポート可能）で text/csv + attachment で返す。
@app.get("/api/tags/export")
async def export_tags() -> Response:
    csv_bytes, filename = await tag_controller.build_export_csv()
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# タグの CSV 一括インポート（IMPL-202608261630 T3 / ADR-0061）。name一致でupsert、parent_nameで階層指定。
# multipart/form-data の file を受け取り、Knowledge MCP の import_tag_batch へ委ねる。
@app.post("/api/tags/import", response_model=tag_controller.TagImportResponse)
async def import_tags(file: UploadFile = File(...)):
    return await tag_controller.import_tags_csv(await file.read())


# ---------------------------------------------------------------------------
# 管理UI: /api/tag-folders*（タグフォルダマスタ, ADR-0072）
# ---------------------------------------------------------------------------
# タグフォルダは parent_tag_id による is-a 階層とは独立した分類表示専用メタデータ。
# search_knowledge の検索結果・スコアには一切影響しない。
@app.get("/api/tag-folders", response_model=tag_controller.TagFolderListResponse)
async def list_tag_folders():
    return await tag_controller.list_tag_folders()


@app.post("/api/tag-folders", status_code=201)
async def create_tag_folder(body: tag_controller.TagFolderCreateRequest) -> dict:
    return await tag_controller.create_tag_folder(body)


@app.put("/api/tag-folders/{folder_id}")
async def update_tag_folder(
    folder_id: int, body: tag_controller.TagFolderUpdateRequest
) -> dict:
    return await tag_controller.update_tag_folder(folder_id, body)


# タグフォルダの移動（ADR-0073）。親フォルダを付け替える。移動先が自分自身または子孫の場合は
# Knowledge MCP の TagError→409（グローバルハンドラ）。ルート更新（name/description）とは別経路。
@app.put("/api/tag-folders/{folder_id}/move")
async def move_tag_folder(
    folder_id: int, body: tag_controller.TagFolderMoveRequest
) -> dict:
    return await tag_controller.move_tag_folder(folder_id, body)


@app.delete("/api/tag-folders/{folder_id}", status_code=204)
async def delete_tag_folder(folder_id: int) -> Response:
    await tag_controller.delete_tag_folder(folder_id)
    return Response(status_code=204)


# タグフォルダを兄弟集合内で1つ上／下へ並べ替える（ADR-0074）。body: {"direction": "up" | "down"}。
@app.patch("/api/tag-folders/{folder_id}/reorder")
async def reorder_tag_folder(
    folder_id: int, body: tag_controller.TagReorderRequest
) -> dict:
    return await tag_controller.reorder_tag_folder(folder_id, body)


# ---------------------------------------------------------------------------
# 検証機能: /api/verification/*（IMPL-202608260909 T10、質問→タグ→情報源の検索精度検証）
# ---------------------------------------------------------------------------
# 検証実行（run）は select_tags→search_knowledge を順に呼び、失敗時も 200 系で status="error" を
# 返す（verification_controller 内で捕捉。409 グローバルハンドラは経由しない, 0章/10章）。
@app.get(
    "/api/verification/questions",
    response_model=verification_controller.VerificationQuestionListResponse,
)
def list_verification_questions(
    keyword: str | None = None, limit: int = 20, offset: int = 0
):
    return verification_controller.list_questions(keyword, limit, offset)


@app.post(
    "/api/verification/questions",
    status_code=201,
    response_model=verification_controller.VerificationQuestionSummary,
)
def create_verification_question(
    body: verification_controller.VerificationQuestionCreateRequest,
):
    return verification_controller.create_question(body)


# CSV 一括インポート（IMPL-202608261022 T14 / ADR-0054）。常に新規追加（重複判定なし）。
# {question_id} を取る GET/PUT/DELETE より前に登録し、パスパラメータに誤って一致しないようにする。
@app.post(
    "/api/verification/questions/import",
    response_model=verification_controller.VerificationImportResponse,
)
async def import_verification_questions(file: UploadFile = File(...)):
    return verification_controller.import_questions_csv(await file.read())


@app.get(
    "/api/verification/questions/{question_id}",
    response_model=verification_controller.VerificationQuestionDetail,
)
def get_verification_question(question_id: int):
    return verification_controller.get_question_detail(question_id)


@app.put(
    "/api/verification/questions/{question_id}",
    response_model=verification_controller.VerificationQuestionSummary,
)
def update_verification_question(
    question_id: int,
    body: verification_controller.VerificationQuestionUpdateRequest,
):
    return verification_controller.update_question(question_id, body)


@app.delete("/api/verification/questions/{question_id}", status_code=204)
def delete_verification_question(question_id: int) -> Response:
    verification_controller.delete_question(question_id)
    return Response(status_code=204)


@app.post(
    "/api/verification/questions/{question_id}/run",
    response_model=verification_controller.VerificationRunOut,
)
async def run_verification_question(question_id: int):
    return await verification_controller.run_question(question_id)


@app.put(
    "/api/verification/runs/{run_id}/evaluation",
    response_model=verification_controller.VerificationRunOut,
)
def save_verification_evaluation(
    run_id: int, body: verification_controller.VerificationEvaluationRequest
):
    return verification_controller.save_evaluation(run_id, body)


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
