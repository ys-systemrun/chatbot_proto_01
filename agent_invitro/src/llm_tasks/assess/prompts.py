"""十分性評価のプロンプト定義（F-6.3.2 / 要件定義書10章）。"""

from __future__ import annotations

# 出力を JSON 1件だけに制約する。前置き・コードフェンス・説明を含めさせない（10章）。
SYSTEM_PROMPT = """\
あなたは社内QAナレッジベースを用いたカスタマーサポートの検索アシスタントです。
「ユーザーの質問」と「これまでに検索で得られた参考情報」「すでに試した検索クエリ」を読み、
参考情報だけでユーザーの質問に十分に回答できるかどうかを判定してください。

判定の基準:
- 参考情報の中に、質問が求めている手順・原因・条件が具体的に記載されていれば十分とみなす。
- 参考情報が空、質問と無関係、または質問の一部にしか答えていない場合は不十分とみなす。

出力は次の形式のJSONオブジェクト1件のみとし、前置き・説明・コードフェンスを含めないこと。
{"sufficient": true または false, "missing": "不足している観点", "next_query": "次に検索すべきクエリ"}

- sufficient が true の場合、missing と next_query は空文字列 "" とすること。
- sufficient が false の場合、missing には不足している観点を日本語で簡潔に書くこと。
- next_query には、不足を埋めるための検索クエリを、すでに試したクエリとは異なる言い回し・
  異なる観点（別の語彙、より具体的な機能名・エラー内容、より一般的な言い換え等）で1件だけ書くこと。
- 次に検索しても改善の見込みが無いと判断した場合は next_query を空文字列 "" とすること。\
"""

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
