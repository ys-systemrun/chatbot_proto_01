import requests

def get_embedding(
    url:str,
    model_name:str,
    text:str,
):
    res = requests.post(
        url,
        json={
            "model": model_name,
            "input": text
        }
    )
    return res.json()["data"][0]["embedding"]