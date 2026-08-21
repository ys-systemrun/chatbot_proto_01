"""chatbot_invitro Terraform デプロイオーケストレータ（コンテナ内 Python 版, ADR-0040）。

旧 terraform/scripts/*.ps1 の置き換え。Windows PowerShell 5.1 + CP932 固有の不具合
（native stderr 昇格 / Get-Content 誤デコード / -target 分割 / パイプ破損）を、
Linux コンテナ内の Python + subprocess のリスト引数 + boto3 で構造的に回避する。
"""

__version__ = "0.1.0"
