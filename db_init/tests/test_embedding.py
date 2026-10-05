"""get_embedding の provider 分岐の単体テスト（IMPL-202608101616 4.3）。

boto3 / requests は monkeypatch でモックし、実際の外部呼び出しは行わない。
"""

import json
import os
import sys

import boto3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import embedding


class _FakeBody:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class _FakeBedrockClient:
    def __init__(self, payload):
        self._payload = payload
        self.last_kwargs = None

    def invoke_model(self, **kwargs):
        self.last_kwargs = kwargs
        return {"body": _FakeBody(self._payload)}


def test_bedrock_titan(monkeypatch):
    fake = _FakeBedrockClient({"embedding": [0.1, 0.2]})
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)

    vec = embedding.get_embedding(
        "bedrock", None, "amazon.titan-embed-text-v2:0", "text", "ap-northeast-1"
    )
    assert vec == [0.1, 0.2]
    assert json.loads(fake.last_kwargs["body"]) == {"inputText": "text"}


def test_bedrock_cohere(monkeypatch):
    fake = _FakeBedrockClient({"embeddings": [[0.3, 0.4]]})
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)

    vec = embedding.get_embedding(
        "bedrock", None, "cohere.embed-multilingual-v3", "text", "ap-northeast-1"
    )
    assert vec == [0.3, 0.4]


def test_lmstudio(monkeypatch):
    class _Resp:
        def json(self):
            return {"data": [{"embedding": [9.0]}]}

    captured = {}

    def fake_post(url, json=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(embedding.requests, "post", fake_post)

    vec = embedding.get_embedding("lmstudio", "http://lm/v1/embeddings", "nomic", "hi")
    assert vec == [9.0]
    assert captured["json"] == {"model": "nomic", "input": "hi"}
