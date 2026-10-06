"""十分性評価のプロンプト定義（F-6.3.2 / 要件定義書10章）。"""

from __future__ import annotations

from ...prompt_store import load_prompt

# 出力を JSON 1件だけに制約する。前置き・コードフェンス・説明を含めさせない（10章）。
# 文面は agent_invitro/prompts/assess.md（ADR-0099 §3）。
SYSTEM_PROMPT = load_prompt("assess")

# ループ内で評価対象として渡す参考情報1件あたりの本文の切り詰め長。プロンプトの肥大化と
# 十分性評価のレイテンシ増を抑えるための上限（回答生成側は切り詰めずに全文を使う）。
CONTENT_HEAD_CHARS = 600


def build_user_content(
    question: str, results: list[dict], tried_queries: list[str]
) -> str:
    """system プロンプトを除いたユーザーメッセージ本文を構築する（F-6.3.2）。"""
    if results:
        blocks = []
        for i, r in enumerate(results, start=1):
            content = str(r.get("content", ""))[:CONTENT_HEAD_CHARS]
            blocks.append(f"({i}) タイトル: {r.get('title', '')}\n本文: {content}")
        knowledge = "\n\n".join(blocks)
    else:
        knowledge = "（検索結果は0件でした）"

    tried = "\n".join(f"- {q}" for q in tried_queries) or "（なし）"

    return (
        f"[ユーザーの質問]\n{question}\n\n"
        f"[これまでに検索で得られた参考情報]\n{knowledge}\n\n"
        f"[すでに試した検索クエリ]\n{tried}"
    )
