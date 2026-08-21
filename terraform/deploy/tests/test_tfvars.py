import pytest

from src import tfvars
from src.errors import DeployError

REQ_DB = ["vpc_id", "private_subnet_ids", "rds_engine_version", "bedrock_embedding_model_id", "embedding_vector_dim"]
REQ_APP = ["bedrock_chat_model_id", "bedrock_embedding_model_id", "embedding_vector_dim"]


def _clear(monkeypatch):
    for k in set(REQ_DB + REQ_APP):
        monkeypatch.delenv(f"TF_VAR_{k}", raising=False)


def test_validate_database_ok(monkeypatch):
    _clear(monkeypatch)
    for k in REQ_DB:
        monkeypatch.setenv(f"TF_VAR_{k}", "x")
    tfvars.validate("database")  # 例外が出なければ OK


def test_validate_app_ok(monkeypatch):
    _clear(monkeypatch)
    for k in REQ_APP:
        monkeypatch.setenv(f"TF_VAR_{k}", "x")
    tfvars.validate("app")


def test_validate_reports_only_missing(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TF_VAR_vpc_id", "vpc-1")  # これだけ設定
    with pytest.raises(DeployError) as exc:
        tfvars.validate("database")
    msg = str(exc.value)
    assert "private_subnet_ids" in msg
    assert "vpc_id" not in msg  # 設定済みは列挙されない


def test_blank_value_treated_as_missing(monkeypatch):
    _clear(monkeypatch)
    for k in REQ_DB:
        monkeypatch.setenv(f"TF_VAR_{k}", "x")
    monkeypatch.setenv("TF_VAR_rds_engine_version", "   ")  # 空白のみ
    with pytest.raises(DeployError) as exc:
        tfvars.validate("database")
    assert "rds_engine_version" in str(exc.value)


def test_unknown_layer(monkeypatch):
    with pytest.raises(DeployError):
        tfvars.validate("bogus")
