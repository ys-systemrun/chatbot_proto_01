# ADR-0005: タグの関連テーブル化（将来のツリー構造対応を見据えて）

- ステータス: Accepted
- 日付: 2026-08-04
- 関連: `docs/requirement/202608041002.md`, ADR-0003, 実装指示書 `docs/implementation_handoff/202608041013_implementation.md`

## コンテキスト

要件定義書 Open Issue #5（tagsのスキーマ表現）および実装指示書0節にて、`qa_original` に `tags TEXT[]` 配列カラムを追加する案を暫定採用していた。しかし、将来的にタグ自体の管理機能（タグの木構造化、親子関係を持たせた分類階層の構築等）が必要になる可能性があることが判明した。配列カラム方式ではタグはただの文字列の集合であり、タグ同士の階層関係やタグ単体でのメタデータ（親タグ、表示順等）を表現できない。

## 決定

タグは **`tag` マスタテーブルと `qa_tag` 関連テーブルによる正規化されたリレーショナル構造** で表現する。`tag` テーブルには自己参照の `parent_tag_id` カラムを持たせ、将来のツリー構造（タグの親子階層）に対応できるようにする。

```sql
CREATE TABLE IF NOT EXISTS tag (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_tag_id INTEGER REFERENCES tag(id)
);

CREATE TABLE IF NOT EXISTS qa_tag (
    qa_id TEXT NOT NULL REFERENCES qa_original(uuid),
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    PRIMARY KEY (qa_id, tag_id)
);
```

`qa_original` には `tags` カラムは追加しない（`title TEXT` カラムのみ追加する。ADR-0003参照）。

## 検討した代替案

- **`qa_original.tags TEXT[]` 配列カラム方式**（当初の暫定案）: 実装・クエリはシンプルだが、タグ単体の管理（リネーム、階層化、表示順、タグごとの説明文等）ができない。タグ管理機能が必要という要望が明確になったため見送った。

## 結果・影響

- タグの追加・リネーム・階層変更が `tag` テーブルの更新のみで完結し、QAレコード側への一括更新が不要になる（配列カラム方式だと全QAレコードの配列値を書き換える必要があった）。
- `parent_tag_id` により将来的なツリー構造（例: 「操作方法」の子に「積算システム操作方法」を置く等）を表現できる余地を残す。ただし **本ADRの時点ではツリー構造を用いた検索（親タグ指定時に子タグも含めて検索する等）の実装はスコープ外とし、将来の拡張ポイントとして列を用意するに留める**。
- `search_knowledge` の `tags` フィルタは、MVPでは指定されたタグ名との完全一致検索のみとし、階層を辿った祖先/子孫タグの展開は行わない（この挙動は要件定義書 Open Issue として別途追加する）。
- QARepository の検索クエリは `qa_original` ⋈ `question_altered` に加えて `qa_tag` ⋈ `tag` の結合が必要になり、既存 `search_similar` よりSQLがやや複雑になる。`qa_tag.tag_id` へのインデックスを付与しパフォーマンスを担保する。
- 既存データの補完（バックフィル）では、まず `data/exportjson_withguid.json` 内のユニークなタグ名を `tag` テーブルに投入し、その後各QAレコードとタグの紐付けを `qa_tag` に投入する2段階の処理が必要になる（実装指示書4.3節参照）。既存データのタグはフラットな一覧のため、`parent_tag_id` は初期値としてはすべて `NULL` とし、階層構造の設計・入力は別途の検討事項とする。
- タグのマスタ管理（登録・リネーム・階層編集）をどのコンポーネントが担うか（Knowledge MCPのスコープ内か、別の管理ツールか）は未確定であり、Open Issueとして追加管理する。
