"""_make_embed_fn の provider 分岐の単体テスト（IMPL-202608101616 4.2）。

boto3 / requests は monkeypatch でモックし、実際の外部呼び出しは行わない。
"""

import os
import sys

import boto3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from knowledge_mcp.mcp import server


class _FakeBody:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        import json

        return json.dumps(self._payload).encode("utf-8")


class _FakeBedrockClient:
    def __init__(self, payload):
        self._payload = payload
        self.last_kwargs = None

    def invoke_model(self, **kwargs):
        self.last_kwargs = kwargs
        return {"body": _FakeBody(self._payload)}


def test_bedrock_titan_branch(monkeypatch):
    fake = _FakeBedrockClient({"embedding": [0.1, 0.2, 0.3]})
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)

    embed = server._make_embed_fn("bedrock", None, "amazon.titan-embed-text-v2:0", "ap-northeast-1")
    vec = embed("hello")

    assert vec == [0.1, 0.2, 0.3]
    import json

    body = json.loads(fake.last_kwargs["body"])
    assert body == {"inputText": "hello"}


def test_bedrock_cohere_branch(monkeypatch):
    fake = _FakeBedrockClient({"embeddings": [[0.4, 0.5]]})
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)

    embed = server._make_embed_fn("bedrock", None, "cohere.embed-multilingual-v3", "ap-northeast-1")
    vec = embed("bonjour")

    assert vec == [0.4, 0.5]
    import json

    body = json.loads(fake.last_kwargs["body"])
    assert body == {"texts": ["bonjour"], "input_type": "search_document"}


def test_lmstudio_branch_unchanged(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [1.0, 2.0]}]}

    def fake_post(url, json=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(server.requests, "post", fake_post)

    embed = server._make_embed_fn("lmstudio", "http://lm/v1/embeddings", "nomic")
    vec = embed("hi")

    assert vec == [1.0, 2.0]
    assert captured["url"] == "http://lm/v1/embeddings"
    assert captured["json"] == {"model": "nomic", "input": "hi"}
