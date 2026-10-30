# ADR-0106: トラブルシューティング記事に、DB の採番に依存しない識別子 uuid を持たせる

- ステータス: Proposed（実装済み。既存環境でシードを流し、全記事に uuid が入ったことを確認したら Accepted にする）
- 日付: 2026-10-30
- 関連: ADR-0076（トラブルシューティング記事の取り込み）, ADR-0066（全データインポート）, ADR-0105（Redmine Wiki のエラー対応を CSV で取り込む）

## コンテキスト

`troubleshooting_article` の識別子は `id SERIAL` だけで、DB の採番に依存する。記事を取り込み直す（DB を作り直す・全データインポートする）と番号が変わりうる。
評価のゴールデンセットは出典を `troubleshooting:<id>` で書いており、`evals/golden/README.md` にも「記事を再インポートしたら確認する」と注意書きがある。
広場 QA は `hiroba_qa_original.uuid`（元データの GUID）を持ち、取り込み直しても変わらない。

ADR-0105 で、Redmine Wiki 由来の CSV に行ごとの UUID（`guid` 列）を持たせた。これを DB にも入れ、HTML 由来の記事にも同じ性質の識別子を持たせる。

## 決定

1. **マイグレーション 0011 で `troubleshooting_article.uuid TEXT` と一意索引を追加する。** NULL を許す（既存行は次回シードで埋めるため）。
2. **値はシードが入れる。**
   - CSV 由来: `guid` 列の値。空なら下の導出値。
   - HTML 由来: `(source_key, title)` から UUID v5 で導出する（名前空間は `troubleshooting_import.ARTICLE_UUID_NAMESPACE`。変えない）。同じ元データからは何度取り込んでも同じ値になる。
3. **既存行は次回シードでバックフィルする。** `(source_key, title)` が一致し `uuid` が NULL の行に、uuid だけを UPDATE する。本文・embedding・タグなどは従来どおり上書きしない。ADR-0066 の全データインポートで 0011 より前のダンプを入れた場合も、次回シードで埋まる。
4. **新しいタイトルの記事の uuid が、別タイトルの既存行ですでに使われていれば投入しない（警告を出す）。** 元データ側でタイトルを変えた場合に、同じ記事が二重に入るのを防ぐ。DB 側の記事を直すか消してから再シードする。
5. **全データエクスポート（web_backend の `export/tables.py`）の列と DDL に `uuid` を加える。** db_init の EXPORT_MODE・import_data は列を `information_schema` から読むため変更不要。
6. **検索結果の出典 ID（`Document.id`）は本 ADR では変えない。** 切り替えは ADR-0107 で行った。

## 影響

- 既存環境では、0011 適用後の最初のシードで全記事に uuid が入る（ログの `backfilled_uuids`）。
- 管理画面で記事のタイトルを編集しても uuid は変わらない（シードは既存行の uuid を上書きしない）。DB を作り直して元データから取り込み直した場合は、元データのタイトルから導出した値になる。
- 出典 ID の uuid への切り替えは ADR-0107 を参照。
