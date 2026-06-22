import uuid

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import os

from src.embedding import get_embedding
from src.db import DB
from src.llm import generate_answer_stateful, SummarizeLLM
from src.models.stateless.message import Message as ModelMessage

app = FastAPI()

DATABASE_URL = os.environ["DATABASE_URL"]
LMSTUDIO_CHAT_URL = os.environ["LMSTUDIO_CHAT_URL"]
MODEL_CHAT = os.environ["MODEL_CHAT"]
EMBEDDING_URL = os.environ["LMSTUDIO_EMBEDDING_URL"]
EMBEDDING_MODEL = os.environ["MODEL_EMBEDDING"]

_SYSTEM_PROMPT = """\
あなたは当社製品専門の優秀なカスタマーサポートAIです。
顧客からのトラブルや操作方法に関する質問に対し、参考情報をもとにルールに沿って解決策を提案してください。

応答のルール:
1. まずは「お問い合わせいただきありがとうございます」と挨拶してください。
2. 参考情報に回答に必要な情報が含まれる場合は、解決策はステップ・バイ・ステップで手順を分けて提示し、回答の最後には「こちらの方法で解決しない場合は、お手数ですが有人サポートまでご連絡ください」と添えてください。
3. 問い合わせ内容があいまいで参考情報に回答に必要な情報が得られなかった場合は、「申し訳ございません、ご提供いただいた情報が不足しています。より詳しい情報を入力してください。」と回答してください。
4. 問い合わせ内容が当社製品と関係がない場合は、「申し訳ございません、当社の製品に関する操作方法やトラブルシューティングの範疇を超えるため、現在お手持ちの情報からはお答えすることができませんでした。」と回答してください。
"""

_summarizer = SummarizeLLM(LMSTUDIO_CHAT_URL, MODEL_CHAT)


class Message(BaseModel):
    order: int
    role: str
    content: str


class Summary(BaseModel):
    content: str
    summarized_upto: int


class Request(BaseModel):
    session_id: str | None = None  # None の場合はサーバー側で新規発行
    text: str
    messages: list[Message]
    summary: Summary


class Response(BaseModel):
    session_id: str
    messages: list[Message]
    summary: Summary


def _summarize_oldest(
    messages: list[Message],
    summary: Summary,
    n: int = 3,
) -> tuple[list[Message], Summary]:
    """order の昇順で先頭 n 件を要約し、残りメッセージと更新後の Summary を返す。

    既存の summary.content がある場合は新しい要約テキストを末尾に追記する。
    """
    sorted_msgs = sorted(messages, key=lambda m: m.order)
    to_summarize = sorted_msgs[:n]
    rest = sorted_msgs[n:]

    msgs = [ModelMessage(m.order, m.role, m.content) for m in to_summarize]
    new_text = _summarizer.summarize(msgs, summary.content)

    # combined = (
    #     f"{summary.content}\n{new_text}".strip() if summary.content else new_text
    # )

    return rest, Summary(
        content=new_text,
        summarized_upto=to_summarize[-1].order,
    )


@app.post("/ask-sl", response_model=Response)
def ask(req: Request):
    session_id = req.session_id or str(uuid.uuid4())
    messages = list(req.messages)
    summary = req.summary

    # 15件以上のとき、order が若い順に 3 件を要約して messages から除外する
    if len(messages) >= 15:
        messages, summary = _summarize_oldest(messages, summary)

    # 1. embedding
    emb = get_embedding(EMBEDDING_URL, EMBEDDING_MODEL, req.text)

    # 2. 類似検索
    with DB(DATABASE_URL) as db:
        results = db.search_similar(emb, 3)

    # 3. コンテキスト生成
    context = "\n".join(
        f"Q_similar: {r[0]}\nQ_original: {r[2]}\nA_original: {r[1]}" for r in results
    )

    # 4. 新規メッセージの order 決定
    next_order = (max(m.order for m in messages) + 1) if messages else 1

    # 5. ユーザーメッセージ追加
    user_msg = Message(
        order=next_order,
        role="user",
        content=f"参考情報:\n{context}\n\n質問:\n{req.text}",
    )
    messages.append(user_msg)

    # 6. LLM 用メッセージリスト構築（system + 要約 + 履歴を order 順に並べる）
    system_content = _SYSTEM_PROMPT
    if summary.content:
        system_content += f"\n\n## これまでの会話の要約:\n{summary.content}"

    llm_messages = [{"role": "system", "content": system_content}]
    llm_messages += [
        {"role": m.role, "content": m.content}
        for m in sorted(messages, key=lambda m: m.order)
    ]

    # 7. LLM 回答生成
    answer = generate_answer_stateful(LMSTUDIO_CHAT_URL, MODEL_CHAT, llm_messages)

    # 8. アシスタントメッセージ追加
    assistant_msg = Message(order=next_order + 1, role="assistant", content=answer)
    messages.append(assistant_msg)

    return Response(
        session_id=session_id,
        messages=messages,
        summary=summary,
    )
