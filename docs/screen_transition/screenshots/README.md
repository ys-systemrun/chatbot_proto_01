# screenshots/

[`../画面遷移図.md`](../画面遷移図.md) から参照する画面イメージ画像を格納します。

## 現状

全 13 画面とも**実際のアプリを起動して撮影したスクリーンショット（PNG）**です。
ワイヤーフレームのプレースホルダ（SVG）はすべて実画面に差し替え済みで、残っていません。

## ファイル一覧と対応画面

| ファイル | 画面 | URL |
|----------|------|-----|
| `01_chat.png` | チャット | `/` |
| `02_evaluated_messages.png` | 評価済みメッセージ一覧 | `/evaluated_messages` |
| `03_qa_list.png` | 広場QA 一覧 | `/admin/qa` |
| `04_qa_form.png` | 広場QA 新規・編集 | `/admin/qa/new` ・ `/admin/qa/:id` |
| `05_altered_list.png` | 言い換え質問文 一覧 | `/admin/hiroba_question_altered` |
| `06_altered_form.png` | 言い換え 新規・編集 | `/admin/hiroba_question_altered/new` ・ `/:id` |
| `07_troubleshooting_list.png` | トラブルシューティング記事 一覧 | `/admin/troubleshooting` |
| `08_troubleshooting_form.png` | トラブルシューティング記事 編集 | `/admin/troubleshooting/:id` |
| `09_tags.png` | タグ管理 | `/admin/tags` |
| `10_verification_list.png` | 検証質問 一覧 | `/admin/verification` |
| `11_verification_detail.png` | 検証詳細 | `/admin/verification/:id` |
| `12_verification_form.png` | 検証質問 新規・編集 | `/admin/verification/new` ・ `/:id/edit` |
| `13_export.png` | 全データエクスポート | `/admin/export` |

## スクリーンショットの撮影・差し替え手順

1. `docker-compose.yml` でバックエンド／DB／フロントを起動する。
2. ブラウザで上表の各 URL を開く。
3. スクリーンショットを撮影し、**同じ番号・名前**で PNG として上書き保存する（パス変更が不要なため本文の修正も不要）。
4. 画面を追加した場合は掲載順に合わせて番号を振り直し、[`../画面遷移図.md`](../画面遷移図.md) の画像パスと
   上表もあわせて更新する。

> 命名規則（`NN_画面名`）と番号順は [`../画面遷移図.md`](../画面遷移図.md) の「3. 画面別スクリーンショット & 説明」の
> 掲載順（チャット → 評価 → 広場QA → 言い換え → トラブルシューティング → タグ → 検証 → エクスポート）に対応しています。
> 画面を追加する際は掲載順に合わせて番号を振り直してください。
