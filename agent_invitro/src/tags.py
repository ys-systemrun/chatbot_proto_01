"""会話タグのマージ・継続判定・情報源検索ロジック（IMPL-202608261345 T6, ADR-0057 / ADR-0062 / ADR-0063）。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TagState:
    id: int
    name: str
    score: float
    missed_turns: int


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


def compute_conversation_tags(
    new_tags: list[dict],
    client_tags: list,  # main/api/server.py の ConversationTag のリスト（id/name/score/missed_turns属性を持てばよい）
    max_missed_turns: int,
    max_tags: int,
) -> list[TagState]:
    """select_tags結果とクライアント由来タグをマージし、継続タグを判定する（要件定義書6.4.3節）。

    戻り値はそのリクエストの検索（search_with_merged_tags）にも、
    レスポンスの継続タグ（Response.tags）にも、同一の集合として使う。
    """
    new_by_id = {t["id"]: t for t in new_tags}
    updated: dict[int, TagState] = {}

    # 1-2. クライアント由来タグ: 再選択されていれば missed_turns=0・score更新、
    #      されていなければ missed_turns+1
    for ct in client_tags:
        if ct.id in new_by_id:
            nt = new_by_id[ct.id]
            updated[ct.id] = TagState(
                id=ct.id, name=nt["name"], score=nt["score"], missed_turns=0
            )
        else:
            updated[ct.id] = TagState(
                id=ct.id, name=ct.name, score=ct.score, missed_turns=ct.missed_turns + 1
            )

    # 3. 新規タグの追加（クライアント側に無かったもの）
    for t in new_tags:
        if t["id"] not in updated:
            updated[t["id"]] = TagState(
                id=t["id"], name=t["name"], score=t["score"], missed_turns=0
            )

    # 4. missed_turns がしきい値を超えたタグを破棄
    tags = [t for t in updated.values() if t.missed_turns <= max_missed_turns]

    # 5. 上限件数を超える場合は missed_turns 降順 → score 昇順で間引く
    if len(tags) > max_tags:
        tags.sort(key=lambda t: (-t.missed_turns, t.score))
        tags = tags[:max_tags]

    return tags


async def search_with_merged_tags(
    search_tool,
    extract_results_fn,  # server.py の _extract_results をそのまま渡す
    query: str,
    merged_tags: list[TagState],
    top_k: int,
) -> list[dict]:
    """マージタグ全件を1回の tags 引数にまとめて search_knowledge を単一呼び出しする
    （ADR-0062 / 要件定義書5.1節）。検証機能（ADR-0060）と同一方式。

    ADR-0058/0059 により tags 引数は完全一致AND条件から「タグ類似度によるソフトな
    ランキングシグナル」へ変わり、ADR-0057 が対応していた0件化リスクは解消された。
    そのため、タグ別複数回呼び出し・フォールバック呼び出し・QA単位の最大スコア統合は
    不要となり、マージタグ全件（0件なら空配列）を1回で渡すだけでよい。tags=[] は
    ADR-0059 により tags 未指定と同じ扱い（埋め込み類似度のみ）になる。
    """
    raw = await search_tool.ainvoke(
        {"query": query, "tags": [t.name for t in merged_tags], "top_k": top_k}
    )
    return extract_results_fn(raw)[:top_k]
