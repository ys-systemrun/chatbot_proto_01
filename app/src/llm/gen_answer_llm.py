"""LLM を使って回答を生成するクラス。"""
from __future__ import annotations

import requests


def _build_prompt(context: str, question: str) -> str:
    return f"""\
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
{question}"""


class GenerateAnswerLLM:
    """コンテキストと質問から LLM で回答を生成するクラス。

    `SummarizeLLM` と同じ呼び出しパターンを使用する。
    インスタンスに URL とモデル名を保持するため、呼び出しのたびに渡す必要がない。
    """

    def __init__(self, url: str, model_name: str) -> None:
        """
        Args:
            url:        LLM の chat completions エンドポイント URL。
                        例: ``"http://host.docker.internal:1234/v1/chat/completions"``
            model_name: 使用するモデル名。
        """
        self._url = url
        self._model_name = model_name

    def generate_stateful(self, messages: list[dict]) -> str:
        """メッセージ履歴を渡して回答を生成する（ステートフル版）。

        Args:
            messages: LLM API に渡すメッセージリスト（ConversationState.messages_as_dicts() の出力）。

        Returns:
            LLM が生成した回答テキスト。
        """
        res = requests.post(
            self._url,
            json={"model": self._model_name, "messages": messages},
        )
        return res.json()["choices"][0]["message"]["content"]

    def generate(self, context: str, question: str) -> str:
        """コンテキストと質問を渡して回答を生成する（ステートレス版）。

        Args:
            context:  参考情報テキスト（DB の検索結果から組み立てたもの）。
            question: ユーザーの質問テキスト。

        Returns:
            LLM が生成した回答テキスト。
        """
        prompt = _build_prompt(context, question)
        res = requests.post(
            self._url,
            json={
                "model": self._model_name,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return res.json()["choices"][0]["message"]["content"]
