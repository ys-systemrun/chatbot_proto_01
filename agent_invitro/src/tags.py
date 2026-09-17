"""select_tags 戻り値の正規化と Alias 一致対象テキストの構築（ADR-0063 / ADR-0086）。

会話タグ機構（TagState・compute_conversation_tags・search_with_merged_tags）は ADR-0084 に
より廃止され、会話文脈の管理は summary（会話要約）へ一本化された。本モジュールに残るのは
select_tags の呼び出しに引き続き必要な langchain-mcp-adapters 戻り値の正規化ヘルパー
（_mcp_result_to_dicts / _extract_selected_tags, ADR-0063）と、ADR-0086 の Alias 確定タグ
向けに生テキストを組み立てる build_alias_match_text である。
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _mcp_result_to_dicts(raw) -> list[dict]:
    """langchain-mcp-adapters のツール戻り値を、payload候補となる dict のリストへ正規化する（ADR-0063）。

    langchain-mcp-adapters はバージョンにより戻り値が dict（structuredContent相当）/
    JSON文字列 / bytes / (content, artifact)タプル / テキストブロックのlist
    （例: [{"type": "text", "text": "<json>"}]）のいずれにもなり得る。旧実装は
    dict/str/tuple しか扱えず、テキストブロックの list を無言で握りつぶしていたため、
    select_tags の結果（selected）が常に空になっていた（ADR-0063 コンテキスト）。

    ここでは想定される全形式を吸収し、目的キー（selected/results）を含み得る dict の
    候補を優先順に返す。テキストブロックは text を JSON として展開する。取り出せない
    場合は空リストを返す（呼び出し側で診断ログを出す）。
    """
    # 1) (content, artifact) タプルは content（先頭要素）を対象にする
    if isinstance(raw, tuple):
        raw = raw[0] if raw else None
    # 2) bytes / JSON文字列は JSON としてデコードする
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    # 3) dict はそのまま payload 候補
    if isinstance(raw, dict):
        return [raw]
    # 4) list は各要素を dict 候補へ展開する（テキストブロックは text を JSON 展開）
    if isinstance(raw, list):
        dicts: list[dict] = []
        for item in raw:
            if isinstance(item, (bytes, bytearray)):
                try:
                    item = item.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):  # MCP テキストブロック {"type":"text","text":"<json>"}
                    parsed = _try_json(text)
                    if isinstance(parsed, dict):
                        dicts.append(parsed)
                        continue
                    if isinstance(parsed, list):
                        dicts.extend(d for d in parsed if isinstance(d, dict))
                        continue
                dicts.append(item)  # 通常の結果dict等（テキストブロックでない dict）
            elif isinstance(item, str):
                parsed = _try_json(item)
                if isinstance(parsed, dict):
                    dicts.append(parsed)
                elif isinstance(parsed, list):
                    dicts.extend(d for d in parsed if isinstance(d, dict))
        return dicts
    return []


def _try_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_selected_tags(raw) -> list[dict]:
    """select_tags の戻り値（{"selected": [...]}）から selected 配列を頑健に取り出す（ADR-0063）。

    langchain-mcp-adapters のバージョン差（dict / JSON文字列 / タプル / bytes /
    テキストブロックの list）を _mcp_result_to_dicts で吸収する。取り出せない場合は
    診断ログ（戻り値の型と先頭一部）を出したうえで空リストを返す。
    """
    for payload in _mcp_result_to_dicts(raw):
        selected = payload.get("selected")
        if isinstance(selected, list):
            return selected
    logger.warning(
        "select_tags 応答から selected を取り出せませんでした: type=%s head=%s",
        type(raw).__name__,
        repr(raw)[:300],
    )
    return []


_QUESTION_MARKER = "質問:\n"


def _extract_question_from_content(content: str) -> str:
    """user メッセージの content から実際の質問文だけを取り出す（ADR-0086 決定4）。

    user メッセージの content は web_backend / agent_invitro いずれの実装でも
    「参考情報:\n{context}\n\n質問:\n{text}」という固定テンプレートで構築されるため、
    "質問:\n" 以降の部分文字列のみを抽出する。過去に提示された記事の文言（参考情報）を
    誤って Alias 一致させないための処理である。マーカーが見つからない場合は content 全文を
    フォールバックとして返す。参考情報側にも "質問:\n" が含まれ得るため、最後の出現位置を採る。
    """
    idx = content.rfind(_QUESTION_MARKER)
    if idx == -1:
        return content
    return content[idx + len(_QUESTION_MARKER):]


def build_alias_match_text(
    req_text: str,
    messages: list,  # order/role/content 属性を持つメッセージのリスト
    summarized_upto: int,
) -> str:
    """select_tags へ渡す alias_match_text を構築する（ADR-0086 決定4）。

    「今回の発話（req_text）＋未要約履歴のうち role="user" の質問文」を結合する。
    role="assistant" のメッセージ、および要約済み（order <= summarized_upto）の履歴は
    対象外とする（発注者確認済み、REQ-202609091730 6.2〜6.3節）。LLM 推論に使う
    query（言い換え質問）と異なり、固定エラー文言をそのまま保持した生テキストを対象に
    Alias 一致させるためのテキストである。
    """
    parts = [req_text]
    for m in sorted(messages, key=lambda m: m.order):
        if m.role != "user":
            continue
        if m.order <= summarized_upto:
            continue
        parts.append(_extract_question_from_content(m.content))
    return "\n".join(p for p in parts if p)
