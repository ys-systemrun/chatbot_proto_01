import os

import pytest

from src import config
from src.errors import DeployError


def write_env(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_and_env_population(tmp_path, monkeypatch):
    for k in list(os.environ):
        if k.startswith("TF_VAR_") or k in ("AWS_PROFILE", "AWS_SESSION_TOKEN"):
            monkeypatch.delenv(k, raising=False)
    env = write_env(
        tmp_path,
        "\n".join(
            [
                "STATE_BUCKET=my-bucket",
                "AWS_REGION=us-east-1",
                "AWS_ACCOUNT_ID=123456789012",
                "NAME_PREFIX=chatbot-invitro",
                "AWS_ACCESS_KEY_ID=AKIA_TEST",
                "AWS_SECRET_ACCESS_KEY=secret",
                'TF_VAR_vpc_id=vpc-123',
                'TF_VAR_private_subnet_ids=["subnet-a","subnet-b"]',
                "TF_VAR_embedding_vector_dim=1024",
                "TF_VAR_multi_az=false",
            ]
        ),
    )
    cfg = config.load_config(env)

    assert cfg.state_bucket == "my-bucket"
    assert cfg.aws_region == "us-east-1"
    assert cfg.state_key_database == "database/state.tfstate"
    assert cfg.state_key_app == "app/state.tfstate"

    # 共通値のマッピング
    assert os.environ["TF_VAR_aws_region"] == "us-east-1"
    assert os.environ["TF_VAR_state_bucket"] == "my-bucket"
    assert os.environ["TF_VAR_aws_account_id"] == "123456789012"
    assert os.environ["TF_VAR_name_prefix"] == "chatbot-invitro"
    assert os.environ["AWS_DEFAULT_REGION"] == "us-east-1"
    assert os.environ["TF_VAR_state_key_database"] == "database/state.tfstate"

    # TF_VAR_* は verbatim（JSON リストの角括弧・数値・真偽をそのまま保持）
    assert os.environ["TF_VAR_private_subnet_ids"] == '["subnet-a","subnet-b"]'
    assert os.environ["TF_VAR_vpc_id"] == "vpc-123"
    assert os.environ["TF_VAR_embedding_vector_dim"] == "1024"
    assert os.environ["TF_VAR_multi_az"] == "false"

    # 明示キーがプロファイルに優先し、プロファイルは掃除される
    assert os.environ["AWS_ACCESS_KEY_ID"] == "AKIA_TEST"
    assert "AWS_PROFILE" not in os.environ


def test_quotes_stripped_but_not_json(tmp_path):
    env = write_env(
        tmp_path,
        'STATE_BUCKET="b"\nAWS_REGION=us-east-1\nTF_VAR_x="quoted"\nTF_VAR_list=["a"]\n',
    )
    cfg = config.load_config(env)
    assert cfg.state_bucket == "b"  # 引用符は剥がす
    assert os.environ["TF_VAR_x"] == "quoted"
    assert os.environ["TF_VAR_list"] == '["a"]'  # JSON は剥がさない


def test_comments_and_blanks_ignored(tmp_path):
    env = write_env(
        tmp_path,
        "# comment\n\nSTATE_BUCKET=b\nAWS_REGION=us-east-1\n# TF_VAR_should_not=appear\n",
    )
    config.load_config(env)
    assert "TF_VAR_should_not" not in os.environ


def test_missing_state_bucket_raises(tmp_path):
    env = write_env(tmp_path, "AWS_REGION=us-east-1\n")
    with pytest.raises(DeployError):
        config.load_config(env)


def test_missing_region_raises(tmp_path):
    env = write_env(tmp_path, "STATE_BUCKET=b\n")
    with pytest.raises(DeployError):
        config.load_config(env)


def test_missing_env_file_raises(tmp_path):
    with pytest.raises(DeployError):
        config.load_config(tmp_path / "nope.env")


def test_profile_used_when_no_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    env = write_env(tmp_path, "STATE_BUCKET=b\nAWS_REGION=us-east-1\nAWS_PROFILE=myprof\n")
    config.load_config(env)
    assert os.environ["AWS_PROFILE"] == "myprof"
