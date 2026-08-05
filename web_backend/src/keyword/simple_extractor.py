"""語彙リストと正規表現を使った軽量なキーワード抽出器の実装。"""
from __future__ import annotations

import re

# カスタマーサポート文脈でよく登場する汎用語彙
_DEFAULT_VOCAB: list[str] = [
    # 認証・アカウント
    "ログイン", "ログアウト", "パスワード", "認証", "ライセンス", "有効化", "登録",
    # セットアップ
    "インストール", "アンインストール", "アップデート", "更新", "初期化", "リセット",
    # 動作状態
    "起動", "再起動", "シャットダウン", "フリーズ", "クラッシュ", "応答なし",
    # 問題・障害
    "エラー", "障害", "不具合", "バグ", "失敗", "できない", "動かない",
    # データ操作
    "保存", "削除", "復元", "バックアップ", "コピー", "移行",
    # 接続・通信
    "接続", "切断", "ネットワーク", "通信", "同期",
    # 印刷・出力
    "印刷", "スキャン", "出力", "表示",
    # 設定
    "設定", "環境設定", "オプション", "カスタマイズ",
]

# エラーコード・バージョン番号などのコードパターン
# 例: E-1234 / ERR001 / 0x80070057 / v1.2.3
_CODE_PATTERN = re.compile(
    r"\b[A-Z]{1,4}[-_]?\d{3,6}\b"   # E-1234, ERR001
    r"|0x[0-9A-Fa-f]{2,8}"           # 0x80070057
    r"|\bv\d+\.\d+[\.\d]*\b",        # v1.2.3
    re.IGNORECASE,
)


class SimpleKeywordExtractor:
    """語彙リストへのマッチングとコードパターン検出でキーワードを抽出する。

    LLM を使わないため高速で、API 呼び出しコストが発生しない。
    精度は語彙リストの品質に依存するため、製品固有の用語は
    ``extra_vocab`` で追加することを推奨する。
    """

    def __init__(
        self,
        extra_vocab: list[str] | None = None,
        max_keywords: int = 5,
    ) -> None:
        """
        Args:
            extra_vocab:  デフォルト語彙に追加する製品固有のキーワードリスト。
            max_keywords: 抽出するキーワードの最大数。デフォルトは 5。
        """
        self._vocab = _DEFAULT_VOCAB + (extra_vocab or [])
        self._max = max_keywords

    def extract(self, text: str) -> list[str]:
        """語彙マッチングとコードパターンでキーワードを抽出する。

        語彙マッチングはテキスト内の出現順、コードパターンはその後に続く。
        重複は除去される。
        """
        # 語彙リストとのマッチング（出現順を保持）
        matched = [kw for kw in self._vocab if kw in text]

        # コード・バージョンパターンのマッチング
        codes = _CODE_PATTERN.findall(text)

        # 結合・重複除去（dict.fromkeys で挿入順を保持）
        combined = list(dict.fromkeys(matched + codes))
        return combined[: self._max]
