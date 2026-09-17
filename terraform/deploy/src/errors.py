"""共通例外。"""


class DeployError(Exception):
    """想定内の失敗（前提未達・terraform 失敗・検証エラー等）。

    __main__ が捕捉してメッセージを表示し exit 1 する（旧 common.ps1 の Fail 相当）。
    """


class ServicesNotStable(DeployError):
    """ECS サービスが待機時間内に steady state へ到達しなかった。

    どのサービスが不安定だったかを `services` に持たせ、呼び出し側が
    そのサービスの停止理由・コンテナログを追加取得できるようにする
    （boto3 の WaiterError はサービス名を持たないため独自例外にする）。
    """

    def __init__(self, services: "list[str]", elapsed_sec: int) -> None:
        self.services = list(services)
        self.elapsed_sec = elapsed_sec
        super().__init__(
            f"ECS サービスが安定しませんでした（{elapsed_sec}s 待機）: {', '.join(self.services)}"
        )
