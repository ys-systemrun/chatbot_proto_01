"""シード用の embedding 計算（web_backend/src/embedding.py から移管）。

LM Studio の OpenAI 互換 /v1/embeddings エンドポイントを呼び出す。
web_backend 側はチャット機能（/ask のクエリ embedding 計算）で同等の関数を
引き続き保持する（要件定義書10章）。
"""

import requests


def get_embedding(
    url: str,
    model_name: str,
    text: str,
):
    res = requests.post(
        url,
        json={
            "model": model_name,
            "input": text,
        },
    )
    return res.json()["data"][0]["embedding"]
