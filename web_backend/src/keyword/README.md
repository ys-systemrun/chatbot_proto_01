# web_backend/src/keyword/ — 質問文からのキーワード抽出

ユーザーの質問からキーワードのリストを取り出す部品。`KeywordExtractor` プロトコルに対して、LLM を使わない軽量版と LLM 版の 2 実装を持つ。現時点で web_backend 内に呼び出し元はない。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | `KeywordExtractor` と 2 つの実装クラスを再エクスポートする。 |
| [`base.py`](base.py) | `extract(text) -> list[str]` だけを持つインターフェース `KeywordExtractor`（Protocol）。 |
| [`llm_extractor.py`](llm_extractor.py) | `LLMKeywordExtractor`。チャット API にキーワードをカンマ区切りで出させ、番号等を除去してリスト化する。失敗時は空リストを返す。 |
| [`simple_extractor.py`](simple_extractor.py) | `SimpleKeywordExtractor`。サポート文脈の汎用語彙リストとの一致と、エラーコード・バージョン番号の正規表現で抽出する（API 呼び出しなし）。 |
