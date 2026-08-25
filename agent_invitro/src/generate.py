"""Bedrock (boto3) を使って回答を生成するモジュール（IMPL-202608241104 T6, ADR-0043 / 0章）。

web_backend/src/llm/gen_answer_llm_bedrock.py の GenerateAnswerLLMBedrock と同一の
boto3 bedrock-runtime invoke_model 呼び出し構造を複製したもの（0章: 単発プロンプト生成方式）。
agent_invitro を web_backend から独立させるため、プロンプト定数もここに複製して自己完結させる。
"""

from __future__ import annotations

import boto3

# web_backend/src/llm/gen_answer_llm.py と同一のプロンプト・ラベル（複製）。
_SYSTEM_PROMPT = """\
あなたは当社製品専門の優秀なカスタマーサポートAIです。
顧客からのトラブルや操作方法に関する質問に対し、参考情報をもとにルールに沿って解決策を提案してください。

応答のルール:
1. まずは「お問い合わせいただきありがとうございます」と挨拶してください。
2. 参考情報に回答に必要な情報が含まれる場合は、解決策はステップ・バイ・ステップで手順を分けて提示し、回答の最後には「こちらの方法で解決しない場合は、お手数ですが有人サポートまでご連絡ください」と添えてください。
3. 問い合わせ内容があいまいで参考情報に回答に必要な情報が得られなかった場合は、「申し訳ございません、ご提供いただいた情報が不足しています。より詳しい情報を入力してください。」と回答してください。
4. 問い合わせ内容が当社製品と関係がない場合は、「申し訳ございません、当社の製品に関する操作方法やトラブルシューティングの範疇を超えるため、現在お手持ちの情報からはお答えすることができませんでした。」と回答してください。
"""

_ROLE_LABEL = {"user": "User", "assistant": "Assistant"}


def _build_user_content(
    context: str,
    question: str,
    summary: str = "",
    history: list[dict] | None = None,
) -> str:
    """system プロンプトを除いたユーザーメッセージ本文を構築する。

    Bedrock Claude では system を別フィールドで渡すため system セクションを含まない
    （web_backend の gen_answer_llm_bedrock._build_user_content と同一）。
    """
    parts = []

    if summary:
        parts.append(f"# Conversation Summary\n{summary}")

    if history:
        lines = [
            f"{_ROLE_LABEL.get(m['role'], m['role'])}: {m['content']}"
            for m in history
        ]
        parts.append("# Recent Conversation\n" + "\n".join(lines))

    parts.append(f"# Retrieved Knowledge\n{context}")
    parts.append(f"# Current User Message\n{question}")

    return "\n\n".join(parts)


class GenerateAnswerLLMBedrock:
    """Bedrock (boto3) を使って回答を生成するクラス。

    web_backend の同名クラスと同一のメソッドシグネチャ・呼び出し構造を持つ。
    """

    def __init__(
        self,
        model_id: str,
        region_name: str = "ap-northeast-1",
        max_tokens: int = 4096,
    ) -> None:
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def _invoke(self, system: str, messages: list[dict]) -> str:
        # Bedrock Converse API を使う（invoke_model の Anthropic 生ボディからの変更, Phase 6 の知見）。
        # Converse はモデル非依存の統一フォーマット（content=[{"text": ...}]、type キー無し）を持ち、
        # Anthropic Claude / Amazon Nova 等で同一に動く（tag_selector_mcp の ChatBedrockConverse と同経路）。
        converse_messages = [
            {
                "role": m["role"],
                "content": (
                    m["content"]
                    if isinstance(m["content"], list)
                    else [{"text": m["content"]}]
                ),
            }
            for m in messages
        ]
        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system}],
            messages=converse_messages,
            inferenceConfig={"maxTokens": self._max_tokens},
        )
        blocks = response["output"]["message"]["content"]
        return "".join(b.get("text", "") for b in blocks)

    def generate(
        self,
        context: str,
        question: str,
        summary: str = "",
        history: list[dict] | None = None,
    ) -> tuple[str, str]:
        """構造化プロンプトで回答を生成する。

        Returns:
            (answer, prompt) — 回答テキストと LLM に渡したユーザーメッセージ本文。
        """
        user_content = _build_user_content(context, question, summary, history)
        answer = self._invoke(
            _SYSTEM_PROMPT.strip(),
            [{"role": "user", "content": user_content}],
        )
        return answer, user_content
