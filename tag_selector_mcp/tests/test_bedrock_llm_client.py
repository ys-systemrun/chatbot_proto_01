"""BedrockLLMClient とファクトリの単体テスト（IMPL-202608101616 4.1 / 9章）。

boto3 は monkeypatch でモックし、実際の AWS 呼び出しは行わない。
"""

import os
import sys

import boto3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tag_selector_mcp.infrastructure.llm import create_llm_client
from tag_selector_mcp.infrastructure.llm.bedrock import BedrockLLMClient
from tag_selector_mcp.infrastructure.llm.lmstudio import LMStudioLLMClient


class _FakeBedrockClient:
    def __init__(self):
        self.last_kwargs = None

    def converse(self, **kwargs):
        self.last_kwargs = kwargs
        return {
            "output": {
                "message": {"content": [{"text": '{"tags": ["A"]}'}]}
            }
        }


@pytest.fixture
def fake_bedrock(monkeypatch):
    fake = _FakeBedrockClient()
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)
    return fake


def test_complete_sends_converse_and_returns_text(fake_bedrock):
    client = BedrockLLMClient(model_id="anthropic.claude", region_name="ap-northeast-1")
    out = client.complete("hello")

    assert out == '{"tags": ["A"]}'
    # Converse API の messages 形式で prompt が渡っていること
    assert fake_bedrock.last_kwargs["modelId"] == "anthropic.claude"
    assert fake_bedrock.last_kwargs["messages"] == [
        {"role": "user", "content": [{"text": "hello"}]}
    ]


def test_factory_returns_bedrock_client(fake_bedrock):
    client = create_llm_client(
        "bedrock", bedrock_model_id="anthropic.claude", bedrock_region="ap-northeast-1"
    )
    assert isinstance(client, BedrockLLMClient)


def test_factory_bedrock_requires_model_and_region():
    with pytest.raises(ValueError):
        create_llm_client("bedrock", bedrock_model_id=None, bedrock_region=None)


def test_factory_lmstudio_unchanged():
    client = create_llm_client("lmstudio", "http://x/v1/chat/completions", "m")
    assert isinstance(client, LMStudioLLMClient)


def test_factory_lmstudio_requires_url_and_model():
    with pytest.raises(ValueError):
        create_llm_client("lmstudio", None, None)


def test_factory_unknown_provider():
    with pytest.raises(ValueError):
        create_llm_client("openai")
