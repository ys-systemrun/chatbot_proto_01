import argparse
import os
import pprint
import readline

from src.embedding import get_embedding
from src.db import DB
from src.llm import generate_answer_stateful
from src.models.conversation_state import ConversationState
from src.relevance import (
    RelevanceStrategy,
    DistanceRelevanceStrategy,
    LLMRelevanceStrategy,
    DEFAULT_THRESHOLD,
)
from src import write_chat

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

_NO_MATCH_REPLY = "申し訳ございません。ご質問に適合する情報が見つかりませんでした。お手数ですが有人サポートまでご連絡ください。"


def _build_user_content(context: str, question: str) -> str:
    return f"参考情報:\n{context}\n\n質問:\n{question}"


def _build_strategy(name: str, threshold: float) -> RelevanceStrategy:
    if name == "llm":
        return LLMRelevanceStrategy(LMSTUDIO_CHAT_URL, MODEL_CHAT)
    return DistanceRelevanceStrategy(threshold)


def _chat_once(
    state: ConversationState,
    question: str,
    strategy: RelevanceStrategy,
) -> tuple[str, list[tuple]]:
    """1 ターン分の処理を行い、(回答テキスト, search_similar の結果リスト) を返す。"""
    emb = get_embedding(EMBEDDING_URL, EMBEDDING_MODEL, question)

    with DB(DATABASE_URL) as db:
        results = db.search_similar(emb, 3)

    if not strategy.is_relevant(question, results):
        state.append_message("user", question)
        state.append_message("assistant", _NO_MATCH_REPLY)
        return _NO_MATCH_REPLY, results

    context = "\n".join(
        f"Q_similar: {r[0]}\nQ_original: {r[2]}\nA_original: {r[1]}" for r in results
    )

    state.append_message("user", _build_user_content(context, question))

    answer = generate_answer_stateful(
        LMSTUDIO_CHAT_URL,
        MODEL_CHAT,
        state.messages_as_dicts(),
    )

    state.append_message("assistant", answer)
    return answer, results


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive chatbot")
    parser.add_argument(
        "--relevance",
        choices=["distance", "llm"],
        default="distance",
        help="適合判定ストラテジー: distance=距離閾値(デフォルト), llm=LLM判定",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"distance ストラテジー使用時の距離閾値 (デフォルト: {DEFAULT_THRESHOLD})",
    )
    args = parser.parse_args()

    strategy = _build_strategy(args.relevance, args.threshold)
    print(f"適合判定: {args.relevance} ストラテジー")

    log_path = write_chat.open_log_file()
    write_chat.write_session_start(log_path, args.relevance)
    print(f"ログファイル: {log_path}\n")

    state = ConversationState()
    state.append_message("system", _SYSTEM_PROMPT)
    print(state.messages_as_dicts())
    print("\n")

    print("チャットボットへようこそ。終了するには 'exit' または 'quit' を入力してください。\n")

    turn = 0
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

        turn += 1
        answer, search_results = _chat_once(state, user_input, strategy)
        print(f"\nアシスタント: {answer}\n")
        print("[ConversationState]")
        pprint.pprint(state.messages_as_dicts())
        print()

        write_chat.write_turn(
            log_path,
            turn,
            user_input,
            search_results,
            answer,
            state.messages_as_dicts(),
        )


if __name__ == "__main__":
    main()
