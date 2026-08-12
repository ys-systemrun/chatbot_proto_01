"""load_settings / build_llm の provider 分岐テスト（IMPL-202608101616 4.4）。

langchain_openai / langchain_aws は sys.modules にフェイクを注入してモックし、
実パッケージ・AWS 接続なしで build_llm の分岐を検証する。
"""

from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_invitro.config import load_settings


# --- load_settings -------------------------------------------------------

_BASE_ENV = {
    "KNOWLEDGE_MCP_URL": "http://k/mcp",
    "TAG_SELECTOR_MCP_URL": "http://t/mcp",
}


def _clear(monkeypatch):
    for k in [
        "LLM_PROVIDER",
        "KNOWLEDGE_MCP_URL",
        "TAG_SELECTOR_MCP_URL",
        "LMSTUDIO_CHAT_URL",
        "LMSTUDIO_CHAT_MODEL",
        "BEDROCK_CHAT_MODEL_ID",
        "BEDROCK_REGION",
    ]:
        monkeypatch.delenv(k, raising=False)


def test_load_settings_lmstudio_default(monkeypatch):
    _clear(monkeypatch)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("LMSTUDIO_CHAT_URL", "http://lm/v1/chat/completions")
    monkeypatch.setenv("LMSTUDIO_CHAT_MODEL", "gemma")

    s = load_settings()
    assert s.llm_provider == "lmstudio"
    assert s.lmstudio_chat_url == "http://lm/v1/chat/completions"
    assert s.lmstudio_chat_model == "gemma"


def test_load_settings_lmstudio_missing_raises(monkeypatch):
    _clear(monkeypatch)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    # LMSTUDIO_* 未設定
    with pytest.raises(RuntimeError):
        load_settings()


def test_load_settings_bedrock(monkeypatch):
    _clear(monkeypatch)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", "anthropic.claude")
    monkeypatch.setenv("BEDROCK_REGION", "ap-northeast-1")

    s = load_settings()
    assert s.llm_provider == "bedrock"
    assert s.bedrock_chat_model_id == "anthropic.claude"
    assert s.bedrock_region == "ap-northeast-1"


def test_load_settings_bedrock_missing_raises(monkeypatch):
    _clear(monkeypatch)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    with pytest.raises(RuntimeError):
        load_settings()


# --- build_llm (fake langchain modules) ----------------------------------


def _install_fake_langchain(monkeypatch):
    calls = {}

    fake_openai = types.ModuleType("langchain_openai")

    class ChatOpenAI:
        def __init__(self, **kwargs):
            calls["openai"] = kwargs

    fake_openai.ChatOpenAI = ChatOpenAI

    fake_aws = types.ModuleType("langchain_aws")

    class ChatBedrockConverse:
        def __init__(self, **kwargs):
            calls["bedrock"] = kwargs

    fake_aws.ChatBedrockConverse = ChatBedrockConverse

    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai)
    monkeypatch.setitem(sys.modules, "langchain_aws", fake_aws)
    # llm モジュールを再読込させる
    monkeypatch.delitem(sys.modules, "agent_invitro.llm", raising=False)
    return calls


def test_build_llm_bedrock(monkeypatch):
    calls = _install_fake_langchain(monkeypatch)
    from agent_invitro.llm import build_llm

    build_llm(
        llm_provider="bedrock",
        bedrock_chat_model_id="anthropic.claude",
        bedrock_region="ap-northeast-1",
    )
    assert calls["bedrock"]["model"] == "anthropic.claude"
    assert calls["bedrock"]["region_name"] == "ap-northeast-1"


def test_build_llm_lmstudio(monkeypatch):
    calls = _install_fake_langchain(monkeypatch)
    from agent_invitro.llm import build_llm

    build_llm(
        llm_provider="lmstudio",
        lmstudio_chat_url="http://lm/v1/chat/completions",
        lmstudio_chat_model="gemma",
    )
    assert calls["openai"]["model"] == "gemma"
    assert calls["openai"]["base_url"] == "http://lm/v1"
