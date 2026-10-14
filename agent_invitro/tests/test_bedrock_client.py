"""bedrock-runtime クライアントのタイムアウト設定（ADR-0102）。AWS には接続しない。"""

import boto3
import pytest

from agent_invitro import bedrock_client
from agent_invitro.generate import GenerateAnswerLLMBedrock
from agent_invitro.llm_tasks.assess.bedrock import SufficiencyAssessorBedrock


def test_short_and_generate_timeouts():
    short = bedrock_client.bedrock_config()
    assert (short.connect_timeout, short.read_timeout) == (5, 20)
    assert short.retries == {"mode": "standard", "max_attempts": 3}
    assert bedrock_client.bedrock_config("generate").read_timeout == 60
    with pytest.raises(ValueError):
        bedrock_client.bedrock_config("unknown")


def test_timeouts_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("BEDROCK_CONNECT_TIMEOUT_SEC", "3")
    monkeypatch.setenv("BEDROCK_READ_TIMEOUT_SEC", "15")
    monkeypatch.setenv("BEDROCK_GENERATE_READ_TIMEOUT_SEC", "90")
    monkeypatch.setenv("BEDROCK_MAX_ATTEMPTS", "4")
    assert (bedrock_client.bedrock_config().connect_timeout, bedrock_client.bedrock_config().read_timeout) == (3, 15)
    assert bedrock_client.bedrock_config("generate").read_timeout == 90
    assert bedrock_client.bedrock_config().retries["max_attempts"] == 4


def test_generator_and_assessor_use_their_timeouts(monkeypatch):
    """回答生成は長め（generate）、十分性評価などの短い呼び出しは short を使う。"""
    captured = []
    monkeypatch.setattr(boto3, "client", lambda *a, **k: captured.append(k) or object())
    GenerateAnswerLLMBedrock(model_id="m", region_name="us-east-1")
    SufficiencyAssessorBedrock(model_id="m", region_name="us-east-1")
    assert [k["config"].read_timeout for k in captured] == [60, 20]
