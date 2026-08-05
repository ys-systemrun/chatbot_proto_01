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

# タグ管理ツール（ADR-0006） -------------------------------------------------
TAG_NODE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "parent_tag_id": {"type": ["integer", "null"]},
        "children": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["id", "name", "parent_tag_id"],
}

LIST_TAGS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": TAG_NODE_SCHEMA}},
    "required": ["tags"],
}
