"""ローカル直接処理によるチャット応答生成（POST /api/ask-local）。

LM Studio（`FormatQueryToEmbed` → `get_embedding` → `DB.search_similar` → `GenerateAnswerLLM`）で
完結する経路で、ローカル `docker-compose` 環境向けの実装である。MCP・タグ機構は使わない。

agent_invitro への中継は `agent_controller` が担う。以前は本モジュール内で環境変数
`AGENT_INVITRO_URL` の設定有無により両経路を出し分けていたが、ルート定義の時点でどちらの
実装へ入るかが決まるよう、中継側を別コントローラへ分離した（`AGENT_INVITRO_URL` は廃止）。

スキーマは中継側と共有するため `chat_schemas` にある（`agent_invitro` 側と同一契約）。
"""

import uuid

from src.embedding import get_embedding
from src.db import DB
from src.llm import FormatQueryToEmbed, GenerateAnswerLLM, SummarizeLLM
from src.log import log_format_query, log_generate, log_search
from src.models.stateless.message import Message as ModelMessage
from src.main import config
from src.main.controllers.chat_schemas import Message, Request, Response, Summary


# Message / Summary / Request / Response は chat_schemas から再エクスポートする
# （agent_controller と同一のスキーマを共有するため）。
__all__ = ["Message", "Summary", "Request", "Response", "ask"]


_summarizer = SummarizeLLM(config.LMSTUDIO_CHAT_URL, config.MODEL_CHAT)
_query_formatter = FormatQueryToEmbed(config.LMSTUDIO_CHAT_URL, config.MODEL_CHAT)
_generator = GenerateAnswerLLM(config.LMSTUDIO_CHAT_URL, config.MODEL_CHAT)


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

    return rest, Summary(
        content=new_text,
        summarized_upto=to_summarize[-1].order,
    )


def ask(req: Request) -> Response:
    """LM Studio と ナレッジ データベースを直接使って1ターン分の応答を返す。"""
    conversation_id = req.conversation_id or str(uuid.uuid4())
    messages = list(req.messages)
    summary = req.summary

    # 15件以上のとき、order が若い順に 3 件を要約して messages から除外する
    if len(messages) >= 15:
        messages, summary = _summarize_oldest(messages, summary)

    # 1. 会話履歴と order を事前計算（クエリ整形・LLM 生成で共通利用）
    next_order = (max(m.order for m in messages) + 1) if messages else 1
    history = [
        {"role": m.role, "content": m.content}
        for m in sorted(messages, key=lambda m: m.order)
    ] or None

    # 2. 類似検索用クエリの整形
    formatted_query, format_input = _query_formatter.format(
        req.text,
        summary=summary.content,
        history=history,
    )
    log_format_query(format_input, formatted_query, config.MODEL_CHAT)

    # 3. embedding
    emb = get_embedding(config.EMBEDDING_URL, config.EMBEDDING_MODEL, formatted_query)

    # 4. 類似検索
    with DB(config.DATABASE_URL) as db:
        results = db.search_similar(emb, 3)
    log_search(formatted_query, results, config.EMBEDDING_MODEL)

    # 5. コンテキスト生成
    context = "\n".join(
        f"Q_similar: {r[0]}\nQ_original: {r[2]}\nA_original: {r[1]}" for r in results
    )

    # 6. ユーザーメッセージ追加（コンテキスト込み）
    user_msg = Message(
        order=next_order,
        role="user",
        content=f"参考情報:\n{context}\n\n質問:\n{req.text}",
    )
    messages.append(user_msg)

    # 7. LLM 回答生成
    answer, prompt = _generator.generate(
        context,
        req.text,
        summary=summary.content,
        history=history,
    )
    log_generate(prompt, answer, config.MODEL_CHAT)

    # 8. アシスタントメッセージ追加
    assistant_msg = Message(
        order=next_order + 1,
        role="assistant",
        content=answer,
        input=prompt,
        model=config.MODEL_CHAT,
        evaluation=0,
    )
    messages.append(assistant_msg)

    return Response(
        conversation_id=conversation_id,
        messages=messages,
        summary=summary,
    )
