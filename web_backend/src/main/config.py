"""stateless app（src/main/app.py）とその Controller 群が参照する環境設定。

旧 main/main_stateless.py の module 冒頭にあった環境変数読み取りを集約したもの。
値の意味・既定値の方針は移設元コメントを踏襲する。
"""

import os
from pathlib import Path

# chat 系エンドポイント（/ask-sl）が使う環境変数。管理UIのみを AWS 上で /api/* + 静的配信で
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

# AWS 環境（admin_ui）でのみ設定される中継先（IMPL-202608241104 T11, ADR-0045）。
# 空文字（未設定, ローカル docker-compose）の場合は本プロセス内で直接処理する（LM Studio 直接呼び出し）。
# 非空の場合は /ask-sl を agent_invitro へ丸ごと中継する。
AGENT_INVITRO_URL = os.environ.get("AGENT_INVITRO_URL", "")

# admin_ui → agent_invitro の HTTP タイムアウト（秒, T12）。
AGENT_INVITRO_TIMEOUT = float(os.environ.get("AGENT_INVITRO_TIMEOUT", "120"))

# 管理UI（/api/qa*・/api/tags*）が接続する Knowledge MCP のエンドポイント（IMPL-202608060837）。
KNOWLEDGE_MCP_URL = os.environ.get("KNOWLEDGE_MCP_URL", "http://knowledge_mcp:8100/mcp")

# front_dev の本番ビルド出力（dist/）を配置する静的資産ディレクトリ（ADR-0042）。
# プロセスの CWD 基準で解決する（既定 "static" = /app/static）。存在しない環境（ローカルの
# web_backend。front は vite dev server が別コンテナで配信）では SPA 配信を登録しない。
STATIC_DIR = Path(os.environ.get("STATIC_DIR", "static"))
