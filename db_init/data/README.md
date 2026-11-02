# db_init/data — シード元データ

db_init イメージに `/data` として同梱されるシード元データです（ADR-0034）。
ディレクトリを分け（ADR-0098）、データ本体は git ではなく DVC で管理します（ADR-0097）。
git に入っているのは、このファイルと情報源ごとの `.dvc`（内容ハッシュ）だけです。

| ディレクトリ | `.dvc` | 内容 | 使い方 |
|---|---|---|---|
| `knowledge/` | `knowledge.dvc` | **knowledge DB のスナップショット**（テーブルごとの CSV, PostgreSQL の COPY 形式, 埋め込みなし）と `manifest.json`（ADR-0109）。最初の版は 2026-10-26 の本番データ（`snapshots/legacy_sql/`）から作った | シード: knowledge DB が空なら全 9 テーブルをここから取り込む。`kb-import` の取り込み元、`kb-export` の書き出し先 |
| `embedding_cache/<モデル ID>/` | `embedding_cache.dvc` | 埋め込みのキャッシュ。`embeddings.csv`（列 `text_sha256,embedding`。埋め込み元テキストの SHA-256 → pgvector 形式のベクトル）と `meta.json`。いまは `amazon.titan-embed-text-v2_0`（1024 次元, 4,945 件）のみ（ADR-0109 §5） | 取り込み後に `embedding` を補う。キャッシュに無い行（別モデルのローカル環境など）は埋め込み API で計算する |
| `redmine_error_taiou/` | `redmine_error_taiou.dvc` | **追加用**の情報源。Redmine Wiki のエラー対応ページを整形した CSV（`redmine_error_taiou.csv`, 1 行 = 1 記事, 各行に `uuid`）。顧客名は伏せ字済み。変換は [`../tools/redmine_wiki_to_csv.py`](../tools/redmine_wiki_to_csv.py)（ADR-0105） | シード: `troubleshooting_article`（`source_key=redmine_error_taiou`）に未投入の記事だけを入れる。次の `kb-export` でスナップショットに含まれる |

シードの流れ（db_init の通常起動, ADR-0109 段階 4）: knowledge DB が空ならスナップショットを取り込む → 追加用の記事を入れる
→ 埋め込みが無い行を計算して埋める。データがある DB には取り込まない（取り込み直しは `kb-import`）。
**マイグレーションを追加したら、スナップショットを書き出し直す**（スキーマ版が合わないとシードの取り込みが失敗するため）。
追加用の情報源のパスは `db_init/src/main.py` の `TROUBLESHOOTING_SOURCES` に固定です。

以前のシード元データ（`hiroba_qa/`・`troubleshooting/`, ADR-0108）はスナップショットに置き換えて廃止しました。
中身は git の履歴（`.dvc`）と DVC リモートから取り出せます。CSV の書式のルール（ADR-0108）は、追加用の情報源に引き続き使います。

`error_taiou_o/` を置いた場合、それは CSV に変換する前の Redmine Wiki の保存 HTML（顧客名を含む）です。
git（`.gitignore`）にもイメージ（`../.dockerignore`）にも入りません。

## 操作（リポジトリルートで実行）

```
terraform\dvc.bat pull                          データを取得
terraform\dvc.bat add db_init/data/<ディレクトリ>  変更を記録（.dvc が更新される → git commit）
terraform\dvc.bat push                          DVC リモートへ送る（忘れると他の人・デプロイが取得できない）
```

詳細は `terraform/README.md` の「Phase 0.5: ナレッジデータ（DVC）」を参照してください。

## 構成

| 名前 | 説明 |
|---|---|
| [`knowledge.dvc`](knowledge.dvc) / [`embedding_cache.dvc`](embedding_cache.dvc) / [`redmine_error_taiou.dvc`](redmine_error_taiou.dvc) | 各ディレクトリの DVC ポインタ（内容ハッシュ・ファイル数）。`dvc pull` で展開される |
| [`.gitignore`](.gitignore) | DVC が展開するデータ本体を git の対象外にする（`dvc add` が生成）。加工前の `/error_taiou_o` も対象外にする |
