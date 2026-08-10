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
from ..models.qa import QaError
from ..repository.tag_repository import TagRepository, TagError
from ..services.search_service import SearchService


def register_tools(
    mcp: FastMCP,
    search_service: SearchService,
    tag_repository: TagRepository,
    qa_management_repository: QaManagementRepository,
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
        name="list_categories",
        description="カテゴリ一覧を返す（参照のみ、登録編集は本フェーズ対象外）。",
    )
    def list_categories() -> dict:
        return {"categories": qa_management_repository.list_categories()}
