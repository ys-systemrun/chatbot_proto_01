"""構成別の必須変数チェック（旧 Test-Tfvars 相当）。

設定は .env に一元化され TF_VAR_* として os.environ に載っているため、
ここでは環境変数上に必須 TF_VAR_<name> が非空で存在するかを検査する。
"""

from __future__ import annotations

import os

from .errors import DeployError

REQUIRED = {
    "database": [
        "vpc_id",
        "private_subnet_ids",
        "rds_engine_version",
        "bedrock_embedding_model_id",
        "embedding_vector_dim",
    ],
    "app": [
        "bedrock_chat_model_id",
        "bedrock_embedding_model_id",
        "embedding_vector_dim",
    ],
}


def validate(layer: str) -> None:
    required = REQUIRED.get(layer)
    if required is None:
        raise DeployError(f"未知の layer '{layer}'（database / app のいずれかを指定）")
    missing = [name for name in required if not os.environ.get(f"TF_VAR_{name}", "").strip()]
    if missing:
        raise DeployError(
            f"{layer} 構成の必須変数が .env に未設定です: {', '.join(missing)}\n"
            "  terraform/.env に TF_VAR_<name>= を記入してください（.env.example 参照）。"
        )
