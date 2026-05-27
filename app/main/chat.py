import os

from src.embedding import get_embedding
from src.db import DB
from src.llm import generate_answer_stateful
from src.models.conversation_state import ConversationState

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
2. 解決策はステップ・バイ・ステップで手順を分けて提示してください。
3. 回答の最後には「こちらの方法で解決しない場合は、お手数ですが有人サポートまでご連絡ください」と添えてください。\
"""

_NO_MATCH_REPLY = "申し訳ございません。ご質問に適合する情報が見つかりませんでした。お手数ですが有人サポートまでご連絡ください。"

_DISTANCE_THRESHOLD = 0.3


def _build_user_content(context: str, question: str) -> str:
    return f"参考情報:\n{context}\n\n質問:\n{question}"


def _chat_once(state: ConversationState, question: str) -> str:
    emb = get_embedding(EMBEDDING_URL, EMBEDDING_MODEL, question)

    with DB(DATABASE_URL) as db:
        results = db.search_similar(emb, 3)

    # distance は各行の末尾要素 (index 4)。先頭が最近傍。
    if not results or results[0][4] >= _DISTANCE_THRESHOLD:
        state.append_message("user", question)
        state.append_message("assistant", _NO_MATCH_REPLY)
        return _NO_MATCH_REPLY

    # 閾値未満の結果のみをコンテキストに使用する
    matched = [r for r in results if r[4] < _DISTANCE_THRESHOLD]
    context = "\n".join(
        f"Q_similar: {r[0]}\nQ_original: {r[2]}\nA_original: {r[1]}" for r in matched
    )

    state.append_message("user", _build_user_content(context, question))

    answer = generate_answer_stateful(
        LMSTUDIO_CHAT_URL,
        MODEL_CHAT,
        state.messages_as_dicts(),
    )

    state.append_message("assistant", answer)
    return answer


def main() -> None:
    state = ConversationState()
    state.append_message("system", _SYSTEM_PROMPT)

    print("チャットボットへようこそ。終了するには 'exit' または 'quit' を入力してください。\n")

    while True:
        try:
            user_input = input("あなた: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n終了します。")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("終了します。")
            break

        answer = _chat_once(state, user_input)
        print(f"\nアシスタント: {answer}\n")


if __name__ == "__main__":
    main()
