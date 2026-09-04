"""MCPツール入出力の JSON Schema / 型定義（実装指示書 5.5, 5.6）。

FastMCP は関数シグネチャから入力スキーマを自動生成するが、確定版スキーマを
仕様として明示・共有するため本モジュールに定数として保持する。
"""

# search_knowledge -----------------------------------------------------------
SEARCH_KNOWLEDGE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "top_k": {"type": "integer", "default": 5, "minimum": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"},
        "min_score": {"type": "number", "default": 0.0},
    },
    "required": ["query"],
}

SEARCH_KNOWLEDGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "source_type": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "score": {"type": "number"},
                    "metadata": {"type": "object"},
                },
                "required": [
                    "id",
                    "source_type",
                    "title",
                    "content",
                    "score",
                    "metadata",
                ],
            },
        }
    },
    "required": ["results"],
}

# タグ管理ツール（ADR-0006、IMPL-202608060837 4.3 で description/aliases 追加） ----
TAG_ALIAS_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "alias": {"type": "string"},
    },
    "required": ["id", "alias"],
}

TAG_NODE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "parent_tag_id": {"type": ["integer", "null"]},
        "description": {"type": ["string", "null"]},
        # タグフォルダ（分類表示専用メタデータ, ADR-0072）。検索ロジックには使わない。
        "folder_id": {"type": ["integer", "null"]},
        # 兄弟集合内の表示順序（ADR-0074）。表示専用属性で検索・スコアには関与しない。
        "display_order": {"type": ["number", "null"]},
        "aliases": {"type": "array", "items": TAG_ALIAS_SCHEMA},
        "children": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["id", "name", "parent_tag_id"],
}

LIST_TAGS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": TAG_NODE_SCHEMA}},
    "required": ["tags"],
}

# reorder_tag / reorder_tag_folder の入力（ADR-0074）。direction は up / down のみ。
REORDER_TAG_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "tag_id": {"type": "integer"},
        "direction": {"type": "string", "enum": ["up", "down"]},
    },
    "required": ["tag_id", "direction"],
}

REORDER_TAG_FOLDER_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "folder_id": {"type": "integer"},
        "direction": {"type": "string", "enum": ["up", "down"]},
    },
    "required": ["folder_id", "direction"],
}

# タグフォルダマスタ（分類表示専用メタデータ, ADR-0072 で新設、ADR-0073 で階層化）。
# parent_folder_id による自己参照ツリー構造。children に子フォルダをネストして返す。
# name は表示用ラベルで一意性を持たない（id で識別, ADR-0073 決定1）。
TAG_FOLDER_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "description": {"type": ["string", "null"]},
        "parent_folder_id": {"type": ["integer", "null"]},
        # 兄弟集合内の表示順序（ADR-0074）。表示専用属性で検索には関与しない。
        "display_order": {"type": ["number", "null"]},
        "children": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["id", "name"],
}

LIST_TAG_FOLDERS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"folders": {"type": "array", "items": TAG_FOLDER_SCHEMA}},
    "required": ["folders"],
}

# QA管理ツール（IMPL-202608060837 4.2） --------------------------------------
QA_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "category": {"type": ["string", "null"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "hiroba_question_altered_count": {"type": "integer"},
    },
    "required": ["id", "title", "category", "tags", "hiroba_question_altered_count"],
}

QA_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "question_text": {"type": "string"},
        "answer_text": {"type": "string"},
        "category": {"type": ["object", "null"]},
        "tags": {"type": "array", "items": {"type": "object"}},
        "hiroba_question_altered_count": {"type": "integer"},
    },
    "required": [
        "id",
        "title",
        "question_text",
        "answer_text",
        "category",
        "tags",
        "hiroba_question_altered_count",
    ],
}

LIST_QA_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "keyword": {"type": "string"},
        "category": {"type": "string"},
        "tag_ids": {"type": "array", "items": {"type": "integer"}},
        "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        "offset": {"type": "integer", "default": 0, "minimum": 0},
    },
}

LIST_QA_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": QA_SUMMARY_SCHEMA},
        "total": {"type": "integer"},
    },
    "required": ["items", "total"],
}

LIST_CATEGORIES_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["id", "name"],
            },
        }
    },
    "required": ["categories"],
}
