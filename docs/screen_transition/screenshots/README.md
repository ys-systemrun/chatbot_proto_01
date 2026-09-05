# screenshots/

[`../画面遷移図.md`](../画面遷移図.md) から参照する画面イメージ画像を格納します。

## 現状（プレースホルダ）

現在の `*.svg` は**ワイヤーフレーム風のプレースホルダ（画面イメージの下書き）**です。
アプリのバックエンド／DB を起動して実スクリーンショットを撮影し、差し替えることを想定しています。

## ファイル一覧と対応画面

| ファイル | 画面 | URL |
|----------|------|-----|
| `01_chat.svg` | チャット | `/` |
| `02_evaluated_messages.svg` | 評価済みメッセージ一覧 | `/evaluated_messages` |
| `03_qa_list.svg` | QA 一覧 | `/admin/qa` |
| `04_qa_form.svg` | QA 新規・編集 | `/admin/qa/new` ・ `/admin/qa/:id` |
| `05_altered_list.svg` | 言い換え一覧 | `/admin/hiroba_question_altered` |
| `06_altered_form.svg` | 言い換え新規・編集 | `/admin/hiroba_question_altered/new` ・ `/:id` |
| `07_tags.svg` | タグ管理 | `/admin/tags` |
| `08_verification_list.svg` | 検証一覧 | `/admin/verification` |
| `09_verification_detail.svg` | 検証詳細 | `/admin/verification/:id` |
| `10_verification_form.svg` | 検証新規・編集 | `/admin/verification/new` ・ `/:id/edit` |
| `11_export.svg` | 全データエクスポート | `/admin/export` |

## 実スクリーンショットへの差し替え手順

1. `docker-compose.yml` でバックエンド／DB／フロントを起動する。
2. ブラウザで上表の各 URL を開く。
3. スクリーンショットを撮影し、**同じ番号・名前**で保存する（拡張子は PNG 推奨）。
4. PNG に差し替えた場合は [`../画面遷移図.md`](../画面遷移図.md) の画像パス（`.svg` → `.png`）も更新する。

> 命名規則（`NN_画面名`）と番号順は [`../画面遷移図.md`](../画面遷移図.md) の掲載順に対応しています。
> 番号を維持しておくと差し替え時にパスの修正が最小限で済みます。
