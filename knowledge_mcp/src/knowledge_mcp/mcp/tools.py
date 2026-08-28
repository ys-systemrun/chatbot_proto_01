"""MCPツールのハンドラ定義（実装指示書 5.5, 5.6 / T8, T17、IMPL-202608060837 T2〜T4, T7）。

search_knowledge（読み取り系）、
タグ管理ツール list_tags / create_tag / rename_tag / move_tag / delete_tag /
set_tag_description / add_tag_alias / remove_tag_alias（書き込み系, ADR-0006）、
QA管理ツール list_qa / get_qa / create_qa / update_qa / list_categories（書き込み系, ADR-0014）
を FastMCP インスタンスへ登録する。
"""

from __future__ import annotations

from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from ..repository.qa_management_repository import QaManagementRepository
from ..repository.question_altered_repository import QuestionAlteredRepository
from ..models.qa import QaError
from ..models.question_altered import QuestionAlteredError
from ..repository.tag_repository import TagRepository, TagError
from ..services.search_service import SearchService


def register_tools(
    mcp: FastMCP,
    search_service: SearchService,
    tag_repository: TagRepository,
    qa_management_repository: QaManagementRepository,
    question_altered_repository: QuestionAlteredRepository,
    default_top_k: int = 5,
) -> None:
    # -------------------------------------------------------------- #
    # search_knowledge（読み取り系）
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="search_knowledge",
        description="ナレッジベース（QA等）を意味検索し、関連する文書を score 降順で返す。",
    )
    def search_knowledge(
        query: str,
        top_k: int = default_top_k,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        min_score: float = 0.0,
    ) -> dict:
        documents = search_service.search(
            query, tags=tags, category=category, top_k=top_k
        )
        results = [
            doc.to_dict() for doc in documents if doc.score >= min_score
        ]
        return {"results": results}

    # -------------------------------------------------------------- #
    # タグ管理ツール（書き込み系, ADR-0006）
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="list_tags",
        description="タグを木構造で返す（description / aliases を含む）。parent_tag_id を指定するとその配下を起点に返す。",
    )
    def list_tags(parent_tag_id: Optional[int] = None) -> dict:
        nodes = tag_repository.list_tags(parent_tag_id=parent_tag_id)
        return {"tags": [n.to_dict() for n in nodes]}

    @mcp.tool(
        name="create_tag",
        description="タグを新規作成する。parent_tag_id 指定で子タグとして作成し、description も同時に設定できる。",
    )
    def create_tag(
        name: str,
        parent_tag_id: Optional[int] = None,
        description: Optional[str] = None,
    ) -> dict:
        try:
            node = tag_repository.create_tag(
                name, parent_tag_id=parent_tag_id, description=description
            )
        except TagError as e:
            raise ToolError(str(e))
        return node.to_dict(include_children=False)

    @mcp.tool(
        name="rename_tag",
        description="タグ名を変更する。description を同時に変更することもできる。",
    )
    def rename_tag(
        tag_id: int, new_name: str, description: Optional[str] = None
    ) -> dict:
        try:
            node = tag_repository.rename_tag(tag_id, new_name, description=description)
        except TagError as e:
            raise ToolError(str(e))
        return node.to_dict(include_children=False)

    @mcp.tool(
        name="set_tag_description",
        description="タグの説明文（description）を設定・更新する。null で説明文を消去する。",
    )
    def set_tag_description(tag_id: int, description: Optional[str] = None) -> dict:
        try:
            node = tag_repository.set_tag_description(tag_id, description)
        except TagError as e:
            raise ToolError(str(e))
        return node.to_dict(include_children=False)

    @mcp.tool(
        name="add_tag_alias",
        description="タグに同義語（alias）を追加する。alias が重複する場合はエラーを返す。",
    )
    def add_tag_alias(tag_id: int, alias: str) -> dict:
        try:
            return tag_repository.add_tag_alias(tag_id, alias)
        except TagError as e:
            raise ToolError(str(e))

    @mcp.tool(
        name="remove_tag_alias",
        description="alias を id 指定で削除する。",
    )
    def remove_tag_alias(alias_id: int) -> dict:
        try:
            tag_repository.remove_tag_alias(alias_id)
        except TagError as e:
            raise ToolError(str(e))
        return {"removed": alias_id}

    @mcp.tool(
        name="move_tag",
        description="タグの親を変更する。循環参照になる操作は拒否する。",
    )
    def move_tag(tag_id: int, new_parent_tag_id: Optional[int] = None) -> dict:
        try:
            node = tag_repository.move_tag(tag_id, new_parent_tag_id)
        except TagError as e:
            raise ToolError(str(e))
        return node.to_dict(include_children=False)

    @mcp.tool(
        name="delete_tag",
        description="タグを削除する。qa_tag から参照されている、または子タグを持つ場合は拒否する。削除可能な場合は紐づく tag_alias も同時に削除する。",
    )
    def delete_tag(tag_id: int) -> dict:
        try:
            tag_repository.delete_tag(tag_id)
        except TagError as e:
            raise ToolError(str(e))
        return {"deleted": tag_id}

    @mcp.tool(
        name="import_tag_batch",
        description="複数件のタグをCSV由来の行データからまとめて登録・更新する。name一致でupsertし、"
                    "parent_nameで階層（親タグ）を指定する。",
    )
    def import_tag_batch(rows: List[dict]) -> dict:
        results = tag_repository.import_tag_batch(rows)
        return {
            "total": len(results),
            "success_count": sum(1 for r in results if r["status"] == "success"),
            "results": results,
        }

    @mcp.tool(
        name="export_tags",
        description="全タグを id/name/parent_name/description のフラットな配列で返す"
                    "（親が子より先の階層順、エイリアス除外。CSV組み立ては web_backend 側で行う）。",
    )
    def export_tags() -> dict:
        return {"items": tag_repository.export_tags()}

    # -------------------------------------------------------------- #
    # QA管理ツール（書き込み系, ADR-0014 / IMPL-202608060837）
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="list_qa",
        description="QAを一覧する。keyword(部分一致)/category(名称)/tag_ids(AND)で絞り込み、limit/offsetでページングする。",
    )
    def list_qa(
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        tag_ids: Optional[List[int]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        items, total = qa_management_repository.list_qa(
            keyword=keyword,
            category=category,
            tag_ids=tag_ids,
            limit=limit,
            offset=offset,
        )
        return {"items": [i.to_dict() for i in items], "total": total}

    @mcp.tool(name="get_qa", description="QAの詳細を取得する。")
    def get_qa(qa_id: str) -> dict:
        try:
            detail = qa_management_repository.get_qa(qa_id)
        except QaError as e:
            raise ToolError(str(e))
        return detail.to_dict()

    @mcp.tool(
        name="create_qa",
        description="QAを新規登録する。question_text から embedding を計算し、主となる question_altered を1件生成する。",
    )
    def create_qa(
        title: str,
        question_text: str,
        answer_text: str,
        category_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> dict:
        try:
            detail = qa_management_repository.create_qa(
                title=title,
                question_text=question_text,
                answer_text=answer_text,
                category_id=category_id,
                tag_ids=tag_ids,
            )
        except QaError as e:
            raise ToolError(str(e))
        return detail.to_dict()

    @mcp.tool(
        name="update_qa",
        description="QAを部分更新する。指定フィールドのみ更新（None=変更なし、tag_ids=[]で全解除）。question_text変更時は主質問文行のembeddingのみ再計算する。",
    )
    def update_qa(
        qa_id: str,
        title: Optional[str] = None,
        question_text: Optional[str] = None,
        answer_text: Optional[str] = None,
        category_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> dict:
        try:
            detail = qa_management_repository.update_qa(
                qa_id,
                title=title,
                question_text=question_text,
                answer_text=answer_text,
                category_id=category_id,
                tag_ids=tag_ids,
            )
        except QaError as e:
            raise ToolError(str(e))
        return detail.to_dict()

    @mcp.tool(
        name="import_qa_batch",
        description="複数件のQAをCSV由来の行データからまとめて登録・更新する。uuid空欄は新規、既存は部分更新。存在しないタグ名は自動作成する。行単位でエラーを許容する。",
    )
    def import_qa_batch(rows: List[dict]) -> dict:
        results = qa_management_repository.import_qa_batch(rows, tag_repository)
        return {
            "total": len(results),
            "success_count": sum(1 for r in results if r["status"] == "success"),
            "results": results,
        }

    @mcp.tool(
        name="list_categories",
        description="カテゴリ一覧を返す（参照のみ、登録編集は本フェーズ対象外）。",
    )
    def list_categories() -> dict:
        return {"categories": qa_management_repository.list_categories()}

    # -------------------------------------------------------------- #
    # 言い換え質問文（question_altered）管理ツール（書き込み系, ADR-0064）
    # is_primary=false の言い換え行のみを対象とする。主質問文行（is_primary=true）は
    # 引き続き create_qa/update_qa のみが生成・更新する。
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="list_question_altered",
        description="言い換え行（is_primary=false）を一覧する。qa_id(完全一致)/keyword(text部分一致)で"
                    "絞り込み、limit/offsetでページングする。表示用に qa_original.title を結合して返す。",
    )
    def list_question_altered(
        qa_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        items, total = question_altered_repository.list_question_altered(
            qa_id=qa_id, keyword=keyword, limit=limit, offset=offset
        )
        return {"items": [i.to_dict() for i in items], "total": total}

    @mcp.tool(
        name="get_question_altered",
        description="言い換え行の詳細を id 指定で取得する。",
    )
    def get_question_altered(id: int) -> dict:
        try:
            model = question_altered_repository.get_question_altered(id)
        except QuestionAlteredError as e:
            raise ToolError(str(e))
        return model.to_dict()

    @mcp.tool(
        name="create_question_altered",
        description="言い換え行を新規作成する。qa_id(存在検証)・text から embedding を計算し、"
                    "is_primary=false 固定で1件追加する。",
    )
    def create_question_altered(qa_id: str, text: str) -> dict:
        try:
            model = question_altered_repository.create_question_altered(qa_id, text)
        except QuestionAlteredError as e:
            raise ToolError(str(e))
        return model.to_dict()

    @mcp.tool(
        name="update_question_altered",
        description="言い換え行の text を更新し embedding を再計算する。対象が is_primary=true の"
                    "場合はエラー。qa_id の付け替えは提供しない。",
    )
    def update_question_altered(id: int, text: str) -> dict:
        try:
            model = question_altered_repository.update_question_altered(id, text)
        except QuestionAlteredError as e:
            raise ToolError(str(e))
        return model.to_dict()

    @mcp.tool(
        name="delete_question_altered",
        description="言い換え行を削除する。対象が is_primary=true（主質問文行）の場合はエラー。",
    )
    def delete_question_altered(id: int) -> dict:
        try:
            question_altered_repository.delete_question_altered(id)
        except QuestionAlteredError as e:
            raise ToolError(str(e))
        return {"deleted": id}

    @mcp.tool(
        name="import_question_altered_batch",
        description="複数件の言い換え行をCSV由来の行データからまとめて登録・更新する。id空欄は新規作成"
                    "（is_primary列は無視し常にfalse）、id一致は更新（is_primary=true行はエラー）。"
                    "qa_id の付け替えは拒否する。行単位でエラーを許容する。",
    )
    def import_question_altered_batch(rows: List[dict]) -> dict:
        results = question_altered_repository.import_question_altered_batch(rows)
        return {
            "total": len(results),
            "success_count": sum(1 for r in results if r["status"] == "success"),
            "results": results,
        }

    @mcp.tool(
        name="export_question_altered",
        description="言い換え行（is_primary=false）全件を id/qa_id/text/is_primary の4項目で返す"
                    "（ページングなし、embedding除外。CSV組み立ては web_backend 側で行う）。",
    )
    def export_question_altered() -> dict:
        return {"items": question_altered_repository.export_question_altered()}
