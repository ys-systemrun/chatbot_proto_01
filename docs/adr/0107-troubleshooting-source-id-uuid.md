# ADR-0107: 検索結果のトラブルシューティング記事の出典 ID を、DB の採番から uuid に切り替える

- ステータス: Proposed（実装済み。シードで全記事に uuid が入った環境で、チャットの出典と評価 v3 の `h004` を確認したら Accepted にする）
- 日付: 2026-10-30
- 関連: ADR-0078（トラブルシューティング記事の検索統合）, ADR-0099（ゴールデンセット評価）, ADR-0106（記事の uuid 列）

## コンテキスト

ADR-0106 で `troubleshooting_article.uuid`（元データから決まる識別子）を追加したが、`search_knowledge` が返す出典 ID（`Document.id`）は整数の `id` のままだった。
出典 ID は、評価の採点（`expected_source_ids` の `troubleshooting:<id>`）、会話 DB・検証 DB に保存する出典、チャット画面の参考情報に使われる。
整数の `id` は記事を取り込み直すと変わりうるため、評価の正解が黙って外れる（`evals/golden/README.md` の注意書き）。広場 QA の出典 ID はすでに GUID である。

## 決定

1. **`TroubleshootingRepository.search` の `Document.id` を `uuid` にする。** シード前で uuid が無い行だけは、従来どおり `id` の文字列で代用する（`COALESCE(uuid, id::text)`）。
2. **整数の `id` は `metadata.article_id` に残す。** 管理画面（`/admin/troubleshooting/:id`）や管理用ツールは引き続き整数の `id` を使う（変更しない）。
3. **ゴールデンセット v3 を作り、既定にする。** v2 と同じ問題で、`h004` の `troubleshooting:24` だけを、同じ記事（「ネットワークキーで以下のエラーが発生しました。ログインエラー：ContainerNotFound」）の uuid に置き換える。v2 は書き換えない（使用済みの版は変えない）。
4. **保存済みのデータは移行しない。** 会話 DB・検証 DB にすでに保存された出典の `source_id` は整数の文字列のまま残る（列は VARCHAR で、新旧が混在しても動作に影響はない）。

## 影響

- 出典 ID を整数として扱う箇所は無い（agent_invitro・web_backend・front_dev・evals は文字列として扱う）。front_dev は出典 ID から管理画面へリンクしていない。
- uuid 化した環境で v2 を実行すると、`h004` の出典は一致しない（採点上は出典の取り違えになる）。比較は v3 どうしで行う。
- 過去の会話・検証結果の出典 ID と、新しい出典 ID は形式が異なる。過去のデータから記事を引くときは、整数なら `id`、UUID 形式なら `uuid` で照合する。
