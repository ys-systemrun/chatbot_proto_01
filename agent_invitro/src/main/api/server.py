"""agent_invitro 常駐 HTTP サーバーの起動エントリポイント（ADR-0043 / ADR-0090 決定2）。

Terraform の起動コマンドが参照するモジュールパス（`agent_invitro.main.api.server:app`）を
維持するため、ファイル名と `app` という変数名を変えない。中身は create_app() の呼び出しのみと
し、ルーティング定義・スキーマ定義・実処理は持たない（それぞれ routers/ ・schemas.py ・
usecases/ にある）。
"""

from __future__ import annotations

from .app import create_app

app = create_app()
