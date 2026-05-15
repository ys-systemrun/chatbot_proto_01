import requests

def generate_answer(
        url:str,
        model_name:str,
        context:str, 
        question:str
):
    prompt = f"""
以下の情報を参考にして質問に答えてください。

参考情報:
{context}

質問:
{question}
"""

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