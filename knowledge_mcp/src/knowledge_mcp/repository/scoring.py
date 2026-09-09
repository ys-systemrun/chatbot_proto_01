"""検索スコアリングの共通ヘルパー（ADR-0058 / ADR-0059 / ADR-0078 §結果・影響）。

QARepository と TroubleshootingRepository が同一のスコアリング方針（埋め込み距離→スコア変換、
祖先タグ展開後のタグ構成類似度=Jaccard係数）を共用するため、重複を避けて共通モジュールへ切り出す。
"""

from __future__ import annotations


def distance_to_score(distance: float) -> float:
    """スコア変換式（実装指示書 0節）: score = 1 / (1 + distance)。

    distance は pgvector の <=> 値（小さいほど類似）。暫定式で、精度検証・調整の対象。
    """
    return 1.0 / (1.0 + distance)


def jaccard(a: set, b: set) -> float:
    """タグ構成類似度（Jaccard係数）。

    空集合同士は 0.0（要件定義書6.2節: 両方空でも重なりなし扱い。呼び出し元で
    「タグ未指定」自体は別途分岐しており、ここに来るのは常に入力側が非空のケースのみ）。
    """
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)
