"""bedrock-runtime クライアントの生成（ADR-0102）。

boto3 の既定（接続・読み取りとも 60 秒）のままだと、長く使われずに途中経路で切れた接続を再利用したとき、
応答を 60 秒待ってから再試行することになり、admin_ui の ALB（既定 60 秒）で 504 になる。
読み取りタイムアウトを用途ごとに短くし、切れた接続に当たっても早く再試行へ移るようにする。

- "short": タグ分類・十分性評価・言い換え・逆質問・要約など、出力が短い呼び出し（既定 20 秒）
- "generate": 回答生成（出力が長くなりうるため既定 60 秒）

値は環境変数 BEDROCK_CONNECT_TIMEOUT_SEC / BEDROCK_READ_TIMEOUT_SEC / BEDROCK_GENERATE_READ_TIMEOUT_SEC /
BEDROCK_MAX_ATTEMPTS で上書きできる。
"""

from __future__ import annotations

import os

import boto3
from botocore.config import Config

DEFAULT_CONNECT_TIMEOUT_SEC = 5
DEFAULT_READ_TIMEOUT_SEC = 20
DEFAULT_GENERATE_READ_TIMEOUT_SEC = 60
DEFAULT_MAX_ATTEMPTS = 3


def _env_number(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def bedrock_config(kind: str = "short") -> Config:
    """用途（short / generate）に応じたタイムアウトと再試行の設定。"""
    if kind == "generate":
        read_timeout = _env_number("BEDROCK_GENERATE_READ_TIMEOUT_SEC", DEFAULT_GENERATE_READ_TIMEOUT_SEC)
    elif kind == "short":
        read_timeout = _env_number("BEDROCK_READ_TIMEOUT_SEC", DEFAULT_READ_TIMEOUT_SEC)
    else:
        raise ValueError(f"未知の用途: {kind}")
    return Config(
        connect_timeout=_env_number("BEDROCK_CONNECT_TIMEOUT_SEC", DEFAULT_CONNECT_TIMEOUT_SEC),
        read_timeout=read_timeout,
        # standard モードは読み取りタイムアウト（切れた接続）を含む一時的な失敗を再試行する。
        retries={"mode": "standard",
                 "max_attempts": int(_env_number("BEDROCK_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))},
    )


def make_bedrock_client(region_name: str, kind: str = "short"):
    """タイムアウトと再試行を設定した bedrock-runtime クライアント。"""
    return boto3.client("bedrock-runtime", region_name=region_name, config=bedrock_config(kind))
