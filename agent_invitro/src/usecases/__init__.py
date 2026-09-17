"""ユースケース層（ADR-0090 決定1・決定4）。

HTTP（FastAPI）に依存しない実処理を置く。ルーター（main/api/routers/）から呼ばれ、
例外は `HTTPException` へ変換せずそのまま送出してルーター側に委ねる。
"""
