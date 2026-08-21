"""単一 .env の読み込みと環境変数への反映（ADR-0038 拡張 / ADR-0040）。

すべての設定を一つの .env（既定 <cwd>/.env = terraform/.env）に集約する:
  - AWS_* / STATE_*  … 認証・state 用。ここでマッピングして os.environ / TF_VAR に反映。
  - TF_VAR_*         … terraform 変数。verbatim で os.environ に素通し（リスト/数値/真偽は
                       値をそのまま書く。terraform が HCL/JSON として解釈する）。

os.environ に入れた値は subprocess（terraform）と boto3 の双方が継承・参照する。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import DeployError


def _parse_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE を素直にパース。UTF-8 固定・空行/'#' コメント無視。

    値の前後の引用符は 1 組だけ剥がすが、'[' や '{' で始まる HCL/JSON リテラル
    （例: TF_VAR_private_subnet_ids=["a","b"]）は剥がさない。
    """
    result: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in ("'", '"')
                and value[0] not in "[{"
            ):
                value = value[1:-1]
            result[key] = value
    return result


@dataclass
class Config:
    state_bucket: str
    aws_region: str
    aws_account_id: str
    name_prefix: str
    state_key_database: str
    state_key_app: str
    raw: dict[str, str] = field(default_factory=dict)


def default_env_path() -> Path:
    override = os.environ.get("DEPLOY_ENV_FILE")
    if override:
        return Path(override)
    # コンテナは -w /work/terraform で起動するため cwd/.env = terraform/.env に解決される。
    return Path.cwd() / ".env"


def load_config(env_path: Path | None = None) -> Config:
    path = env_path or default_env_path()
    if not path.exists():
        raise DeployError(
            f".env が見つかりません: {path}\n"
            "  terraform/.env.example をコピーして terraform/.env を作成し、値を記入してください。"
        )
    cfg = _parse_env_file(path)

    state_bucket = cfg.get("STATE_BUCKET", "").strip()
    if not state_bucket:
        raise DeployError(".env の STATE_BUCKET が未設定です。")
    aws_region = cfg.get("AWS_REGION", "").strip()
    if not aws_region:
        raise DeployError(".env の AWS_REGION が未設定です。")
    aws_account_id = cfg.get("AWS_ACCOUNT_ID", "").strip()
    name_prefix = cfg.get("NAME_PREFIX", "").strip()
    state_key_database = cfg.get("STATE_KEY_DATABASE", "").strip() or "database/state.tfstate"
    state_key_app = cfg.get("STATE_KEY_APP", "").strip() or "app/state.tfstate"

    # --- 共通値を TF_VAR / AWS ランタイム変数へ反映（ADR-0038）---
    os.environ["AWS_DEFAULT_REGION"] = aws_region
    os.environ["AWS_REGION"] = aws_region
    os.environ["TF_VAR_aws_region"] = aws_region
    os.environ["TF_VAR_state_bucket"] = state_bucket
    os.environ["TF_VAR_state_key_database"] = state_key_database
    if aws_account_id:
        os.environ["TF_VAR_aws_account_id"] = aws_account_id
    if name_prefix:
        os.environ["TF_VAR_name_prefix"] = name_prefix

    # --- 認証情報: 明示キーがプロファイルに優先。古い値は掃除 ---
    ak = cfg.get("AWS_ACCESS_KEY_ID", "").strip()
    sk = cfg.get("AWS_SECRET_ACCESS_KEY", "").strip()
    st = cfg.get("AWS_SESSION_TOKEN", "").strip()
    prof = cfg.get("AWS_PROFILE", "").strip()
    if ak and sk:
        os.environ.pop("AWS_PROFILE", None)
        os.environ["AWS_ACCESS_KEY_ID"] = ak
        os.environ["AWS_SECRET_ACCESS_KEY"] = sk
        if st:
            os.environ["AWS_SESSION_TOKEN"] = st
        else:
            os.environ.pop("AWS_SESSION_TOKEN", None)
    elif prof:
        os.environ["AWS_PROFILE"] = prof

    # --- .env 内の TF_VAR_* を verbatim で素通し ---
    for key, value in cfg.items():
        if key.startswith("TF_VAR_"):
            os.environ[key] = value

    return Config(
        state_bucket=state_bucket,
        aws_region=aws_region,
        aws_account_id=aws_account_id,
        name_prefix=name_prefix,
        state_key_database=state_key_database,
        state_key_app=state_key_app,
        raw=cfg,
    )
