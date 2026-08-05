import requests

def get_prompt_00(context:str, question:str) -> str:
    return f"""
    以下の情報を参考にして質問に答えてください。

    参考情報:
    {context}

    質問:
    {question}
    """

def get_prompt_with_role(context:str, question:str) -> str:
    return f"""
    # 前提条件
    あなたは、当社製品専門の優秀なカスタマーサポートAIです。

    # 役割と目的
    顧客からのトラブルや操作方法に関する質問に対し、以下の参考情報も使ってルールに沿って解決策を提案してください。

    # 応答のルール
    1. まずは「お問い合わせいただきありがとうございます」と挨拶してください。
    2. 解決策はステップ・バイ・ステップで手順を分けて提示してください。
    3. 回答の最後には「こちらの方法で解決しない場合は、お手数ですが有人サポートまでご連絡ください」と添えてください。

    # 参考情報
    {context}

    # 質問
    {question}
    """


def generate_answer_stateful(
        url: str,
        model_name: str,
        messages: list[dict],
) -> str:
    res = requests.post(
        url,
        json={"model": model_name, "messages": messages}
    )
    return res.json()["choices"][0]["message"]["content"]


def generate_answer(
        url:str,
        model_name:str,
        context:str,
        question:str
):
    prompt = get_prompt_with_role(context, question)

    res = requests.post(
        url,
        json={
            "model": model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
    )
    res = requests.post(
        url,
        json={
            "model": model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
    )

    return res.json()["choices"][0]["message"]["content"]
