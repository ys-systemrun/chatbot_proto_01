"""stateless app（src/main/app.py）とその Controller 群が参照する環境設定。

旧 main/main_stateless.py の module 冒頭にあった環境変数読み取りを集約したもの。
値の意味・既定値の方針は移設元コメントを踏襲する。
"""

import os
from pathlib import Path

# chat 系エンドポイント（/ask-pipeline）が使う環境変数。管理UIのみを AWS 上で /api/* + 静的配信で
# 稼働させる構成では未設定でよく、起動時 KeyError で落とさず空文字として扱う
# （IMPL-202608211050 10章 Open Issue #2）。ローカル docker-compose では compose が値を供給する。
DATABASE_URL = os.environ.get("DATABASE_URL", "")
CONVERSATION_DB_URL = os.environ.get("CONVERSATION_DB_URL", "")

# 全データエクスポート機能（/api/export）が chatbot データベースを読むための接続文字列
# （ADR-0046 / IMPL-202608241600 T14）。AWS 環境では読み取り専用ロール chatbot_export_reader の
# 接続文字列が Terraform secrets 経由で注入される。ローカル docker-compose では未設定のままとし、
# 追加設定なしで動作させるため既存の DATABASE_URL（chatbot データベース）にフォールバックする。
CHATBOT_EXPORT_DB_URL = os.environ.get("CHATBOT_EXPORT_DB_URL") or DATABASE_URL
LMSTUDIO_CHAT_URL = os.environ.get("LMSTUDIO_CHAT_URL", "")
MODEL_CHAT = os.environ.get("MODEL_CHAT", "")
EMBEDDING_URL = os.environ.get("LMSTUDIO_EMBEDDING_URL", "")
EMBEDDING_MODEL = os.environ.get("MODEL_EMBEDDING", "")

# agent_invitro の接続先（ADR-0045 / ADR-0089 決定5）。KNOWLEDGE_MCP_URL 等と同じく
# 「接続先アドレスの設定」であり、経路の切り替えスイッチではない（旧 AGENT_INVITRO_URL は、
# 空文字か否かで中継／ローカル直接処理を出し分けるモードスイッチを兼ねていたため廃止した。
# どちらの実装に入るかは app.py のルート定義で決まる）。
# ローカル docker-compose・AWS のいずれも Service Connect 名は同じであるため既定値を持たせ、
# 変更が必要な場合のみ環境変数で上書きする。
AGENT_INVITRO_BASE_URL = os.environ.get(
    "AGENT_INVITRO_BASE_URL", "http://agent_invitro:8300"
)

# admin_ui → agent_invitro の HTTP タイムアウト（秒, T12）。
AGENT_INVITRO_TIMEOUT = float(os.environ.get("AGENT_INVITRO_TIMEOUT", "120"))

# 管理UI（/api/qa*・/api/tags*）が接続する Knowledge MCP のエンドポイント（IMPL-202608060837）。
KNOWLEDGE_MCP_URL = os.environ.get("KNOWLEDGE_MCP_URL", "http://knowledge_mcp:8100/mcp")

# 検証機能（質問→タグ→情報源の検索精度検証, IMPL-202608260909 T8 / ADR-0049）。
# 検証実行が select_tags を呼び出す tag_selector_mcp のエンドポイント。
TAG_SELECTOR_MCP_URL = os.environ.get(
    "TAG_SELECTOR_MCP_URL", "http://tag_selector_mcp:8200/mcp"
)
# 検証実行時に select_tags / search_knowledge へ都度渡すパラメータ（再現性のため明示的に渡す, 10章）。
VERIFICATION_MAX_TAGS = int(os.environ.get("VERIFICATION_MAX_TAGS", "3"))
VERIFICATION_CONFIDENCE_THRESHOLD = float(
    os.environ.get("VERIFICATION_CONFIDENCE_THRESHOLD", "0.0")
)
VERIFICATION_TOP_K = int(os.environ.get("VERIFICATION_TOP_K", "5"))
VERIFICATION_MIN_SCORE = float(os.environ.get("VERIFICATION_MIN_SCORE", "0.0"))

# front_dev の本番ビルド出力（dist/）を配置する静的資産ディレクトリ（ADR-0042）。
# プロセスの CWD 基準で解決する（既定 "static" = /app/static）。存在しない環境（ローカルの
# web_backend。front は vite dev server が別コンテナで配信）では SPA 配信を登録しない。
STATIC_DIR = Path(os.environ.get("STATIC_DIR", "static"))
