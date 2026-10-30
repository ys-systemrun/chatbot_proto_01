# ADR-0108: DVC で管理するシード元データを CSV に統一し、書式と読み込みの共通ルールを定める

- ステータス: Proposed（ルールの決定。各情報源の CSV 化は、本 ADR の「移行の手順」に沿って個別に行う。進み具合は「移行の状況」）
- 日付: 2026-10-30
- 関連: ADR-0034（シード元データのイメージ同梱）, ADR-0076（トラブルシューティング記事の HTML 取り込み）, ADR-0097（ナレッジデータの DVC 管理）, ADR-0098（情報源別ディレクトリ）, ADR-0105（Redmine Wiki のエラー対応 CSV）, ADR-0106（記事の uuid）

## コンテキスト

`db_init/data/` のシード元データ（DVC 管理）は、情報源ごとに形式がばらばらである。

| ファイル | 形式 | 書式 |
|---|---|---|
| `hiroba_qa/category.csv` | CSV | CRLF・引用符なし。列 `id,name` |
| `hiroba_qa/question_altered.csv` | CSV | LF・`text` だけ引用符。列 `qa_id,"text"` |
| `hiroba_qa/exportjson_withguid.json` | JSON | `guid,title,category,question,answer` の配列。カテゴリは名前で持ち、シード時に `category.csv` で ID に引き直す |
| `troubleshooting/*.html` | HTML | `<h2>` 単位に分割し、`<table>` から列を取り出す（ADR-0076） |
| `redmine_error_taiou/redmine_error_taiou.csv` | CSV | LF・全フィールド引用符・BOM なし（ADR-0105） |

形式ごとに読み込み処理が違い、内容を確認・修正する手段もそろっていない（JSON・HTML は表として見られない）。
CSV にそろえれば、VS Code の Edit csv などで同じように確認・修正でき、変更の差分も追いやすい。

## 決定

### 対象

- **対象は `db_init/data/` のシード元データ**（db_init が DB に投入するもの）。
- **評価の実行結果（`evals/runs/`・`evals/feedback/`, DVC 管理）は対象外。** 出典の一覧・採点の詳細など入れ子の構造を持ち、評価ランナーが出力する（人が編集しない）ため、JSON / JSON Lines のままにする。

### 書式

1. **UTF-8（BOM なし）・LF 改行・全フィールドをダブルクォートで囲む。** Python では `csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")`、`open(..., encoding="utf-8", newline="")`。BOM を付けると Edit csv で先頭の列名が崩れる（ADR-0105）。
2. **1 行目は列名。** 値の中の改行（本文など）はそのまま入れる（引用符の中なので CSV として正しい）。
3. **空欄は空文字列。** DB へは NULL として入れる（`-` などのプレースホルダは使わない）。日時は `YYYY-MM-DD HH:MM:SS`。真偽値は `true` / `false`。

### 構成と列

4. **1 テーブル 1 ファイル。** ファイル名は投入先のテーブルが分かる名前にする。
5. **列名は投入先テーブルの列名にそろえる。** 例: `hiroba_qa_original` なら `uuid,title,question_text,answer_text,category_id`。DB が採番する列（`id SERIAL`）・埋め込み（`embedding`）・作成/更新日時は持たない。
6. **外部キーは DB に入る値（ID）で持つ。** 名前から ID への引き直しはシード時に行わない（例: QA のカテゴリは名前ではなく `category_id`）。
7. **識別子の列を先頭に置き、必ず値を入れる。** 投入のたびに乱数で採番しない（取り込み直しても同じ値になるようにする）。トラブルシューティング記事は `uuid`、QA は `uuid`。
8. **取り込みに使わない補足の列を持ってよい**（例: Redmine の元ページ名 `source_page`）。読み込み処理は読み捨てる。

### 読み込み

9. **列名で読み（`csv.DictReader`）、必須列が無ければエラーにする。知らない列は読み捨てる。**
10. **読み込みは BOM の有無・CRLF/LF・引用符の有無を問わない**（`encoding="utf-8-sig", newline=""`）。人が Excel などで保存し直しても読めるようにするため。書式（上の 1）は書き出す側の約束とする。
11. **パース（CSV → モデル）は DB 非依存の純関数にして単体テストを書く**（既存の `parse_csv_articles` と同じ形）。

### 変換ツール

12. **元の形式から CSV への変換は、1 回限りのツールとして `db_init/tools/` に置く**（シードからは呼ばない）。伏せ字や手作業の補正もツールに書き、変換し直しても同じ結果になるようにする（ADR-0105）。CSV 化した後に CSV を直接直す場合は、以後 CSV を正本とする。

## 移行の手順

1 つの情報源を 1 つの変更（コミットまたはプルリクエスト）にする。各情報源で次を行う。

1. 変換ツールを書き、CSV を作る。
2. シードの読み込みを CSV に切り替え、テストを直す。
3. **変換の前後で DB の中身が同じことを確かめる。** 空の DB に旧形式でシードしたものと CSV でシードしたものを用意し、埋め込み・作成/更新日時を除く全列が一致することを確認する（ADR-0106 の確認と同じく pgvector のコンテナで行う）。
4. 旧形式のファイルを消して `dvc add` → `.dvc` をコミット → `dvc push`。旧形式は DVC の履歴から取り出せる。
5. 環境変数（`QA_ORIGINAL_FILE` など）の既定値・雛形・README・ADR を更新する。

順番は次のとおり。

| 順 | 情報源 | 内容 |
|---|---|---|
| 1 | 広場 QA 本体（`exportjson_withguid.json`） | `hiroba_qa_original.csv` にする。カテゴリを ID にする（上の 6）。読み込み箇所（`seed_helpers.load_qa_original_json`・`backfill_title_and_tags.py`・`evals/runner/golden.py`）と `QA_ORIGINAL_FILE` を変える |
| 2 | トラブルシューティング（`troubleshooting/*.html`） | `parse_articles` で CSV にする。`uuid` は現在の導出値（ADR-0106）をそのまま書き出す（出典 ID とゴールデンセット v3 を変えないため）。元の表を含む `body_html` は列として残し、CSV の読み込みは「`body_html` 列があれば使い、無ければ `guidance` から組み立てる」にする |
| 3 | 既存の CSV（`category.csv`・`question_altered.csv`・`redmine_error_taiou.csv`） | 書式（上の 1）と列名（上の 5）をそろえる。`question_altered` の `qa_id`、Redmine の `guid` → `uuid` など。列名の変更は変換と同時に行わない（3. の比較を単純にするため） |

## 移行の状況

| 順 | 状況 |
|---|---|
| 1 | 済み（2026-10-30）。`hiroba_qa/hiroba_qa_original.csv`（列 `uuid,title,question_text,answer_text,category_id,category_name`。`category_name` は確認用で読み捨て）。変換は `db_init/tools/hiroba_qa_json_to_csv.py`。旧 JSON と CSV で空の DB にシードし、`hiroba_category`・`hiroba_qa_original`（title を含む全列）・タグが一致することを確認した。JSON は削除（DVC の履歴に残る） |
| 2 | 未着手 |
| 3 | 未着手 |

## 影響

- 既存の環境では、中身が同じならシードは何も変えない（広場 QA はテーブル単位の存在チェック、記事は `(source_key, title)` と `uuid` で既存行を上書きしない）。変わるのは `KB_DATA_VERSION`（`.dvc` の内容ハッシュ）だけである。
- 既存の CSV は、書式をそろえるためだけには書き直さない（DVC の版が無駄に増えるため）。手順 3 でまとめて行う。
