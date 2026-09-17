"""Knowledge MCP の search_knowledge 呼び出しと戻り値パース（ADR-0090 決定5 / F-6.7.5）。

再構成前は main/api/server.py の `_extract_results` / `_search_knowledge` として実装されて
いたものを、`/ask-pipeline`・`/ask-agentic` の両ユースケースから共有できるよう独立モジュール
へ移設したもの（挙動は同一, ADR-0090 決定7）。
"""

from __future__ import annotations

import logging

from .tags import _mcp_result_to_dicts

logger = logging.getLogger(__name__)


def extract_results(raw) -> list[dict]:
    """search_knowledge の戻り値から results 配列を頑健に取り出す（ADR-0063）。

    langchain-mcp-adapters のバージョン差で戻り値が「JSON 文字列」「(content, artifact)
    タプル」「dict」「テキストブロックの list」のいずれにもなり得るため、tags.py の
    _mcp_result_to_dicts で全形式を吸収したうえで results を取り出す。旧実装はテキスト
    ブロックの list を results として解釈できず、コンテンツブロックそのものを返して実質
    空コンテキストを生んでいた（ADR-0063 コンテキスト 3.2 節）。
    """
    payloads = _mcp_result_to_dicts(raw)
    for payload in payloads:
        results = payload.get("results")
        if isinstance(results, list):
            return results
    # 「results」キーを持つ dict が無い場合でも、要素自体が結果 dict の list（id/title/
    # content のいずれかを持つ）であればそれを結果とみなす（ラップなしで配列を返す版への保険）。
    if payloads and any(
        ("id" in d or "title" in d or "content" in d) for d in payloads
    ):
        return payloads
    logger.warning(
        "search_knowledge 応答から results を取り出せませんでした: type=%s head=%s",
        type(raw).__name__,
        repr(raw)[:300],
    )
    return []


async def search_knowledge(
    search_tool, query: str, tags: list[str], top_k: int = 3
) -> list[dict]:
    """Knowledge MCP の search_knowledge ツールを1回呼び出し、結果 dict のリストを返す
    （ADR-0084 / ADR-0062）。

    select_tags がその場で選定したタグ名（tags）をそのまま tags 引数へ渡す。ADR-0084 により
    会話タグ機構（ターンをまたいだマージ・継続判定）は廃止されたため、クライアント由来タグとの
    マージは行わない。ADR-0058/0059 により tags 引数は「タグ類似度によるソフトなランキング
    シグナル」であり、tags=[] は tags 未指定と同じ扱い（埋め込み類似度のみ）になる。
    """
    raw = await search_tool.ainvoke(
        {"query": query, "tags": tags, "top_k": top_k}
    )
    return extract_results(raw)


def result_key(result: dict) -> str:
    """検索結果の重複排除キー（F-6.3.7）。`id` を優先し、無ければ `title` を使う。"""
    key = result.get("id")
    if key is None:
        key = result.get("title", "")
    return str(key)


def merge_results(
    accumulated: list[dict], new_results: list[dict], limit: int
) -> list[dict]:
    """蓄積済み結果へ新しい結果を重複排除しつつ追加する（F-6.3.7）。

    `id`（無ければ `title`）が既出のものは捨て、合計が limit 件に達したら打ち切る。
    既存の並び（先にヒットしたものが先）は保持する。
    """
    merged = list(accumulated)
    seen = {result_key(r) for r in merged}
    for r in new_results:
        if len(merged) >= limit:
            break
        key = result_key(r)
        if key in seen:
            continue
        seen.add(key)
        merged.append(r)
    return merged
