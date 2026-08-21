"""共通例外。"""


class DeployError(Exception):
    """想定内の失敗（前提未達・terraform 失敗・検証エラー等）。

    __main__ が捕捉してメッセージを表示し exit 1 する（旧 common.ps1 の Fail 相当）。
    """
