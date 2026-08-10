"""MCPツール入出力の JSON Schema / 型定義（実装指示書 5.7, 5.8）。

FastMCP は関数シグネチャから入力スキーマを自動生成するが、確定版スキーマを
仕様として明示・共有するため本モジュールに定数として保持する。
"""

# select_tags ----------------------------------------------------------------
SELECT_TAGS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "max_tags": {"type": "integer", "default": 3, "minimum": 1},
        "confidence_threshold": {
            "type": "number",
            "default": 0.0,
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
    "required": ["query"],
}

SELECT_TAGS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "selected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "score": {"type": "number"},
                    "path": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "name", "score", "path"],
            },
        }
    },
    "required": ["selected"],
}

# list_taxonomy / reload_taxonomy（ADR-0011） --------------------------------
TAG_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "description": {"type": ["string", "null"]},
        "parent_tag_id": {"type": ["integer", "null"]},
        "aliases": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["id", "name", "parent_tag_id", "aliases"],
}

LIST_TAXONOMY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": TAG_RECORD_SCHEMA}},
    "required": ["tags"],
}

RELOAD_TAXONOMY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reloaded": {"type": "boolean"},
        "tag_count": {"type": "integer"},
    },
    "required": ["reloaded", "tag_count"],
}
