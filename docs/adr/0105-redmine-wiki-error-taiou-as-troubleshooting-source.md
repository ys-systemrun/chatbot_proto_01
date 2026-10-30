# ADR-0105: Redmine Wiki のエラー対応ページを、整形済み CSV にしてトラブルシューティング記事の情報源に加える

- ステータス: Proposed（実装済み。シードで 29 件が投入され、チャットで検索されることを確認したら Accepted にする）
- 日付: 2026-10-30
- 関連: ADR-0034（シード元データのイメージ同梱）, ADR-0076（トラブルシューティング記事の取り込み）, ADR-0078（埋め込み元テキスト）, ADR-0097（ナレッジデータの DVC 管理）, ADR-0098（情報源別ディレクトリ）

## コンテキスト

社内の Redmine（`izumi_v7` プロジェクトの Wiki）に、サポート担当者が書いたエラー対応のページがある。1 ページに 1 つのエラーについて、症状・原因の見立て・対処が自由記述で書かれている。
これをチャットボットの情報源に加えたい。

元データはブラウザの「ページを保存」で保存した HTML（29 ページ）で、次の問題がある。

- 各ページに CSS・JS・画像などの付属ファイルが付き、全体で約 21MB ある。長いファイル名が Windows のパス長の上限で切れているものもある。
- 本文に顧客名（社名）が含まれ、ページ下部には更新者・添付者の社員名がある。
- 本文は表のような構造を持たない（既存の `trouble_shooting.html` の `<table>` 形式とは違う）。

## 決定

1. **整形済み CSV を元データにする。** 保存 HTML から本文（`div.wiki-page`）だけを取り出して、1 行 = 1 記事の CSV（`db_init/data/redmine_error_taiou/redmine_error_taiou.csv`）にする。
   - 列名は `troubleshooting_article` の列名にそろえる（`title`・`error_message`・`guidance`・`cause`・`notes`・`source_updated_at`）。元のページ名を `source_page` に残す（取り込みには使わない）。
   - 先頭列 `guid` に、行ごとの UUID を持たせる。Wiki ページの URL から UUID v5 で決めるので、変換し直しても、タイトルを伏せ字で変えても同じ値になる。現時点では DB には入れない（`troubleshooting_article` に列が無い。取り込み時は読み捨てる）。
   - 本文中にエラーメッセージがあれば `error_message` にも入れる。本文（`guidance`）からは消さない。チャットの検索（埋め込み）と回答に渡す情報は `guidance` を使い、`error_message` は使わないため（ADR-0078）。
   - UTF-8（BOM なし）・LF 改行・全フィールドをダブルクォートで囲む。BOM を付けると VS Code の Edit csv で先頭の列名が崩れるため。
2. **変換は 1 回限りのツールで行い、伏せ字もツールに書く。** `db_init/tools/redmine_wiki_to_csv.py` が変換する。顧客名の伏せ字（`REDACTIONS`）と、本文から取るエラーメッセージ（`ERROR_MESSAGE_FROM_BODY`）をツールに書き、変換し直しても同じ結果になるようにする。更新者名などページ下部は読まない。
3. **CSV を DVC で管理する。** 情報源別ディレクトリ（ADR-0098）として `redmine_error_taiou/` を作り、`redmine_error_taiou.dvc` を git に入れる。デプロイの KB データ版（`KB_DATA_VERSION`）は `db_init/data/*.dvc` を列挙するので、変更なしで対象に入る。
4. **既存の `troubleshooting_article` に別の `source_key`（`redmine_error_taiou`）で入れる。** テーブル・検索・管理画面・タグ付け・評価の出典 ID（`troubleshooting:<id>`）をそのまま使える。マイグレーションは追加しない。
   - db_init の `TROUBLESHOOTING_SOURCES` に CSV を加え、拡張子が `.csv` なら `parse_csv_articles` で読む。
   - `body_html`（必須列）は `guidance` から組み立てる（空行で段落、改行は `<br>`、HTML はエスケープ）。直す場所を CSV の 1 か所にするため。
   - 投入は既存と同じ `(source_key, title)` の冪等挿入。既存環境でも、次のシードで未投入の記事だけが追加される。
5. **加工前の保存 HTML は git にもイメージにも入れない。** `db_init/data/.gitignore` に `/error_taiou_o` を、`db_init/.dockerignore` に `data/error_taiou_o/` を加える（db_init の Dockerfile は `COPY . .` と `COPY data /data` でディレクトリをまるごと入れるため）。

## 影響

- `title` は重複判定の鍵なので、取り込んだ後に CSV のタイトルを変えると、別の記事として二重に入る。タイトルを直すときは、DB 側の記事も管理画面で直すか消す。
- 内容は社内向けの対応メモで、「遠隔で繋ぐ」「様子見をしてもらう」など担当者の視点の言い回しを含む。回答生成はこれを利用者向けに言い換える前提とする。
- 伏せ字は機械的な検索（「様」「株式会社」「コンサル」など）で確認したもので、別の書き方の固有名詞までは保証しない。ページを追加・取り直したときは、変換後の CSV を目で確認する。
- CSV を手で直した場合、ツールで変換し直すとその修正は上書きされる。手で直したら、同じ修正を `REDACTIONS` などツール側にも反映するか、以後は CSV を正本として扱う。
