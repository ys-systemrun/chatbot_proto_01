# web_backend/src/relevance/ — 検索結果の適合判定ストラテジー

類似検索（`DB.search_similar`）の結果がユーザーの質問に答えるのに適合するかを判定するストラテジー群。CLI チャット（`main/chat.py`）が `--relevance` 引数で切り替えて使い、適合しない場合は定型の「見つかりませんでした」応答を返す。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | 基底クラス・2 つの実装・既定閾値 `DEFAULT_THRESHOLD` を再エクスポートする。 |
| [`base.py`](base.py) | 抽象基底クラス `RelevanceStrategy`（`is_relevant(question, results) -> bool`）。 |
| [`distance.py`](distance.py) | `DistanceRelevanceStrategy`。top-1 のコサイン距離が閾値（既定 0.3）未満なら適合とみなす。 |
| [`llm_judge.py`](llm_judge.py) | `LLMRelevanceStrategy`。質問と検索結果を LLM に渡し「はい／いいえ」で適合を判定させる。 |
