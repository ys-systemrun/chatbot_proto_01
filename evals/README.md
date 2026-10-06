# evals/ — 評価ランナーと評価結果

回答品質の改善ループ（ADR-0099）で使う評価ランナーと、その結果を置くディレクトリです。
結果はリポジトリに残し、Claude Code に読ませて原因分析・修正案作成に使います。

```
evals/
  eval.bat            評価ランナーの呼び出し口（python:3.11-slim コンテナで python -m runner を実行）
  .env.example        設定の雛形 → evals/.env にコピーして記入（Git 管理外）
  runner/             評価ランナー本体（標準ライブラリのみ）
  tests/              ランナーのテスト（python -m pytest tests）
  feedback/           人手評価の取り込み結果（<日時>.jsonl）
```

## 準備

1. `evals/.env.example` を `evals/.env` にコピーし、`EVAL_BASE_URL` に admin_ui の URL を書く。
   URL は `apply-app` の完了時に表示される `admin_ui_alb_dns_name` に `http://` を付けたもの。
2. Docker Desktop を起動しておく。admin_ui の ALB は社内ネットワークからのみ到達できる。

## コマンド

| コマンド | 内容 | 段階 |
|---|---|---|
| `evals\eval.bat pull-feedback` | チャット画面で付けた 👍/👎・理由・リリースの増分を `evals/feedback/<日時>.jsonl` に保存する | ① |
| `evals\eval.bat run` | ゴールデンセットの質問を送り、出典と回答を採点する | ③（未実装） |
| `evals\eval.bat compare` | 2回の実行結果を質問単位で比較する | ③（未実装） |
| `evals\eval.bat snapshot` | ナレッジのスナップショットを取り、DVC に追加する | ④（未実装） |

## feedback/<日時>.jsonl の形式

1行が評価済みの回答1件です（👍/👎 のみ。未評価は含まない）。

| キー | 内容 |
|---|---|
| `key` | 重複除去用のキー（会話・順序・評価・理由・評価日時から計算） |
| `conversation_id` / `order` | 会話と、その中の回答の位置 |
| `evaluation` | `good`（👍）/ `bad`（👎） |
| `evaluation_comment` | 評価の理由（未入力なら null） |
| `evaluated_at` / `answered_at` | 評価・理由を最後に変更した日時 / 回答した日時 |
| `question` / `context` | 利用者の質問と、回答時に渡した参考情報（検索結果） |
| `answer` / `model` / `ask_mode` | 回答本文・モデル・方式（`pipeline` / `agentic`） |
| `release_id` / `release` | 回答を生成したリリースと、その内容（コミット・プロンプトのハッシュ・モデル・設定値） |

- 同じ回答でも、評価や理由を付け直すと新しい行として追記されます（変更の履歴が残る）。
- ADR-0099 導入前の評価には `release_id` / `ask_mode` / `evaluated_at` がありません（null）。
