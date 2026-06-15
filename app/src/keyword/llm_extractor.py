"""LLM を使ったキーワード抽出器の実装。"""
from __future__ import annotations

import re

import requests

_SYSTEM_PROMPT = """\
ユーザーの質問から重要なキーワードを最大{max}個抽出してください。
コンマ区切りで出力し、それ以外の文字（説明・番号・記号）は一切含めないこと。
出力例: パスワード,ログイン,エラー\
"""


def _parse_response(raw: str, max_keywords: int) -> list[str]:
    """LLM の出力をキーワードリストにパースする。

    カンマ（全角・半角）・読点・改行で分割し、
    先頭の連番（「1.」「① 」など）を除去する。
    """
    parts = re.split(r"[,、，\n]+", raw)
    result: list[str] = []
    for part in parts:
        cleaned = re.sub(r"^[\d①-⑩]+[.\)．\s]*", "", part.strip())
        if cleaned:
            result.append(cleaned)
    return result[:max_keywords]


class LLMKeywordExtractor:
    """LLM にキーワード抽出を委ねる実装。

    `LLMRelevanceStrategy` と同じ呼び出しパターンを使用する。
    LLM 呼び出しに失敗した場合は空リストを返し、処理を止めない。
    """

    def __init__(
        self,
        url: str,
        model: str,
        max_keywords: int = 5,
    ) -> None:
        """
        Args:
            url:          LLM の chat completions エンドポイント URL。
                          例: ``"http://host.docker.internal:1234/v1/chat/completions"``
            model:        使用するモデル名。
            max_keywords: 抽出するキーワードの最大数。デフォルトは 5。
        """
        self._url = url
        self._model = model
        self._max = max_keywords
        self._system = _SYSTEM_PROMPT.format(max=max_keywords)

    def extract(self, text: str) -> list[str]:
        """LLM を呼び出してキーワードを抽出する。"""
        try:
            res = requests.post(
                self._url,
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": self._system},
                        {"role": "user",   "content": text},
                    ],
                },
            )
            raw = res.json()["choices"][0]["message"]["content"].strip()
            return _parse_response(raw, self._max)
        except Exception:
            # LLM 呼び出し失敗時は空リストを返してフォールバック
            return []
