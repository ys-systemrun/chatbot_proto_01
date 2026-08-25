"""全データエクスポート機能（ADR-0046 / ADR-0047 / IMPL-202608241600 Phase 5）。

chatbot / conversation データベースを読み取り専用でダンプし、CSV / SQL 形式の ZIP を
生成する新規モジュール。既存の src/db.py（DB クラス）・src/conversation_db/（ConversationDB）
とは責務を分離し、ここには search_similar や評価 upsert のロジックを混在させない（3章）。
"""
