"""ZIP アーカイブ生成（IMPL-202608241600 T17、5.5 節）。

追加依存なし。Python 標準ライブラリの zipfile / io のみで、メモリ上の BytesIO に ZIP を
組み立てて返す（10章: 追加依存なし。データ規模が増えた場合の見直しは Open Issue #3）。
"""

from __future__ import annotations

import io
import zipfile


def build_zip(files: dict[str, bytes]) -> bytes:
    """ファイル名 → 中身のバイト列の辞書を ZIP アーカイブのバイト列にまとめる。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)
    return buf.getvalue()
