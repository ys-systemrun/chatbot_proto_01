"""CSV 一括インポートにおける真偽値列の解釈（ADR-0094 決定2・決定3）。

`is_searchable` 列の値の解釈を QA 一括インポート（qa_management_repository）と
言い換え質問文一括インポート（question_altered_repository）で共有する。

- 受理する値: `true` / `false`（大文字小文字を区別しない）、`1` / `0`。
- 列自体が存在しない場合・値が空欄の場合は None（＝「新規は true、既存は変更なし」）を返す。
  呼び出し側は None を部分更新の「変更なし」としてそのまま扱えばよく、新規作成時は
  DB の DEFAULT true（およびツール引数の既定値 True）が効く。
- それ以外の非空値は ValueError を送出する（呼び出し側が当該行のエラーとして報告する）。
"""

from __future__ import annotations

from typing import Optional

_TRUE_VALUES = {"true", "1"}
_FALSE_VALUES = {"false", "0"}


def parse_optional_bool(value, column: str = "is_searchable") -> Optional[bool]:
    """CSV セルの値を Optional[bool] へ変換する。空欄・未指定は None（変更なし）。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{column} must be one of true/false/1/0 (or empty): {value!r}"
    )
