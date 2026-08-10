"""シード用の embedding 計算（web_backend/src/embedding.py から移管）。

provider に応じて接続先を切り替える（IMPL-202608101616 4.3 / ADR-0031）:
- "lmstudio"（既定）: LM Studio の OpenAI 互換 /v1/embeddings エンドポイント。
- "bedrock": Amazon Bedrock InvokeModel API（boto3）。

knowledge_mcp 側（4.2）と同等の分岐を db_hiroba_qa_init 独自の実装として複製する
（コード共有はしない、ADR-0016〜0018 の方針を踏襲）。
web_backend 側はチャット機能（/ask のクエリ embedding 計算）で同等の関数を
引き続き保持する（要件定義書10章）。
"""

import json

import requests


def _bedrock_embed(model_id: str, text: str, region_name: str | None) -> list[float]:
    """Bedrock InvokeModel API で埋め込みベクトルを取得する。

    埋め込み系モデルは Converse API の対象外のため invoke_model() を使う。
    リクエスト/レスポンス形式はモデルにより異なるため model_id で分岐する
    （Titan Text Embeddings を既定、Cohere Embed に対応）。
    """
    # boto3 は bedrock 利用時のみ必要な依存であるため遅延 import する。
    import boto3

    client = boto3.client("bedrock-runtime", region_name=region_name)
    if "cohere" in model_id.lower():
        body = {"texts": [text], "input_type": "search_document"}
        res = client.invoke_model(modelId=model_id, body=json.dumps(body))
        return json.loads(res["body"].read())["embeddings"][0]
    body = {"inputText": text}
    res = client.invoke_model(modelId=model_id, body=json.dumps(body))
    return json.loads(res["body"].read())["embedding"]


def get_embedding(
    provider: str,
    url: str | None,
    model_name: str,
    text: str,
    bedrock_region: str | None = None,
) -> list[float]:
    """provider に応じて埋め込みベクトルを返す。

    Args:
        provider: "lmstudio"（既定）または "bedrock"。
        url: lmstudio 時のみ使用（LMSTUDIO_EMBEDDING_URL）。
        model_name: lmstudio 時のモデル名、または bedrock 時のモデルID。
        text: 埋め込み対象のテキスト。
        bedrock_region: bedrock 時のみ使用（BEDROCK_REGION）。
    """
    if provider == "bedrock":
        return _bedrock_embed(model_name, text, bedrock_region)
    res = requests.post(
        url,
        json={
            "model": model_name,
            "input": text,
        },
    )
    return res.json()["data"][0]["embedding"]
