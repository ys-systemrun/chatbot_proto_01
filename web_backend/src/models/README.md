# web_backend/src/models/ — データモデル

ナレッジ DB のレコードを表すデータクラスと、会話状態・メッセージのモデルを置くフォルダ。会話モデルはサーバー側で状態を持つ旧方式（stateful）と、クライアントが履歴を送る現行方式（stateless）で分かれている。

## 構成

| 名前 | 説明 |
|---|---|
| [`stateful/`](stateful/README.md) | サーバー側で会話状態を保持する方式のモデル（`ConversationState` / `Message` / `Slot`）。 |
| [`stateless/`](stateless/README.md) | stateless 会話で使うメッセージモデル（`Message`）。 |
| [`__init__.py`](__init__.py) | `Category` / `QAOriginal` / `QuestionAltered` と stateful のモデルを再エクスポートする。 |
| [`category.py`](category.py) | カテゴリ（id, name）の dataclass `Category`。 |
| [`qa_original.py`](qa_original.py) | 元 QA（uuid, 質問文, 回答文, カテゴリ ID）の dataclass `QAOriginal`。 |
| [`question_altered.py`](question_altered.py) | 言い換え質問（qa_id, テキスト, 埋め込み, id）の dataclass `QuestionAltered`。DB 投入用のタプル化メソッド `to_tuple` を持つ。 |

`category.py` / `qa_original.py` / `question_altered.py` は現在 web_backend 内から参照されていない。
