"""Terraform 構成ディレクトリ・リポジトリルートの解決。

コンテナ内では `-w /work/terraform`（= リポジトリの terraform/ をマウント）で起動される想定。
デプロイパッケージ自身はイメージ側 (/app) に焼き込まれるため、__file__ ではなく cwd を基点にする。
TERRAFORM_ROOT 環境変数があればそれを優先。
"""

from __future__ import annotations

import os
from pathlib import Path


def tf_root() -> Path:
    override = os.environ.get("TERRAFORM_ROOT")
    return Path(override) if override else Path.cwd()


def repo_root() -> Path:
    # docker build コンテキスト（db_hiroba_qa_init / knowledge_mcp 等）は terraform/ の親に置かれている。
    return tf_root().parent


def bootstrap_dir() -> Path:
    return tf_root() / "bootstrap"


def database_dir() -> Path:
    return tf_root() / "main" / "database"


def app_dir() -> Path:
    return tf_root() / "main" / "app"
