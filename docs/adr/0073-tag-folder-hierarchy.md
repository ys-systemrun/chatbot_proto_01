# ADR-0073: タグフォルダの階層化（フォルダ間の親子関係新設、ADR-0072の限定的な見直し）

- ステータス: Accepted
- 日付: 2026-09-03
- 関連: `docs/requirement/202609030857_タグフォルダ階層化要件定義書.md`、ADR-0072、ADR-0005、ADR-0006、ADR-0058、ADR-0059

本ADRは、ADR-0072が新設した「タグフォルダ」（`hiroba_tag_folder`）を、フラットな1階層のマスタから、フォルダ同士が親子関係を持てるツリー構造へ拡張するものである。ADR-0072の中核判断（タグフォルダは`tag.parent_tag_id`によるis-a階層・`search_knowledge`の検索ロジックとは完全に独立し、管理画面・選択UIの表示専用メタデータに留める）は変更しない。

## コンテキスト

ADR-0072は、タグ運用ガイドライン（`202609021050`）が示した「文脈」「話題」等の分類軸を、タグの一覧・選択UI上でグルーピング表示するための属性としてタグフォルダを新設した。当初のMVPでは、分類軸自体の構造は単純な1階層のフラットな一覧（例:「文脈」「話題」「対象システム」を並べる）を想定しており、`hiroba_tag_folder`にはフォルダ間の階層を持たせていなかった。

運用が進むにつれ、分類軸自体をさらに細分化したいというニーズが生じている（例:「対象システム」フォルダの下に「フロントエンド」「バックエンド」という下位区分を設け、それぞれの下でタグをグルーピングしたい、等）。これはタグ自体のis-a階層（ADR-0005、`parent_tag_id`）とは別の話であり、あくまで分類表示の見出し（フォルダ）自体を入れ子にしたいという要求である。ADR-0072が検討した代替案（`parent_tag_id`ツリーの最上位を分類軸として転用する案）を採らなかった理由（検索ロジックへの意図しない混入）は、フォルダ同士の階層化には当てはまらない。フォルダ階層はタグの検索経路とは無関係な、完全に独立したテーブル（`hiroba_tag_folder`）内で完結するためである。

## 決定

**`hiroba_tag_folder`に、自己参照の`parent_folder_id`列を追加し、フォルダ同士が親子関係（ツリー構造）を持てるようにする。**

```sql
ALTER TABLE hiroba_tag_folder
    ADD COLUMN IF NOT EXISTS parent_folder_id INTEGER REFERENCES hiroba_tag_folder(id);

CREATE INDEX IF NOT EXISTS idx_hiroba_tag_folder_parent_folder_id
    ON hiroba_tag_folder (parent_folder_id);

-- フォルダ名の一意性制約（ADR-0072で追加したUNIQUE）を撤廃する。
-- フォルダの識別は id のみで行い、name の重複を許容する（決定の詳細は次項）。
ALTER TABLE hiroba_tag_folder DROP CONSTRAINT IF EXISTS hiroba_tag_folder_name_key;
```

主要な設計判断は次の3点。

### 1. フォルダ名の一意性制約を撤廃し、id のみを識別子とする

ADR-0072では`tag_alias`と同様の「独立したマスタ＋`name UNIQUE`」方式を踏襲し、`hiroba_tag_folder.name`をグローバルに一意とした。フォルダが階層化されると、「対象システム＞フロントエンド」と「開発工程＞フロントエンド」のように、異なる分類軸の下で同名の子フォルダを使いたいケースが生じうる。これをグローバル一意のまま許容しようとすると、兄弟内一意（`(parent_folder_id, name)`の複合UNIQUE）への変更が必要になるが、今回は仕様をさらに単純化し、**`name`列のUNIQUE制約自体を撤廃**する。フォルダの一意な識別・参照は常に`id`で行い、`name`は表示用ラベルとして重複を許容する。

この変更に伴い、`create_tag_folder`・`rename_tag_folder`が行っていた「同名フォルダの存在チェックによる作成・改名拒否」ロジックは撤廃する。同名フォルダの作成・改名は常に成功する。

### 2. タグへのタグフォルダ割当は、階層のどの深さのフォルダにも許可する（現行を継続）

ADR-0072の「タグフォルダはis-a階層上のどの深さのタグにも付与できる」という考え方を踏襲し、フォルダ階層化後も、`hiroba_tag.folder_id`は中間フォルダ・末端フォルダを問わず、ツリー上の任意のノードを指せる。フォルダ階層は分類の見出し構造を表すのみで、タグの割当先を末端フォルダに限定するような制約は設けない。

### 3. 子フォルダを持つフォルダの削除は、子フォルダを祖父母フォルダへ繰り上げる

既存の`delete_tag_folder`は「`hiroba_tag`から参照されている場合は削除を拒否する」という判断のみを持っていた（ADR-0072）。この判断は変更しない。今回追加するのは、削除対象フォルダが子フォルダを持つ場合の扱いである。

**子フォルダを持つフォルダを削除する場合、その子フォルダ群は削除対象フォルダの親（祖父母フォルダ）へ繰り上げる（`parent_folder_id`を削除対象フォルダの親の値へ更新する）。** 削除対象フォルダがルート（`parent_folder_id IS NULL`）だった場合、子フォルダは新たにルートとなる。

```sql
UPDATE hiroba_tag_folder
SET parent_folder_id = (SELECT parent_folder_id FROM hiroba_tag_folder WHERE id = :deleted_id)
WHERE parent_folder_id = :deleted_id;

DELETE FROM hiroba_tag_folder WHERE id = :deleted_id;
```

削除を拒否する方式（`delete_tag`が子タグ保持時に拒否するのと同じ方式）や、配下を再帰的にまとめて削除するカスケード方式も検討したが、分類見出しの整理（フォルダの統廃合）を行いやすくすることを優先し、繰り上げ方式を採用した。

### 4. フォルダ移動時の循環防止

`move_tag_folder(folder_id, new_parent_folder_id)`を新設し、`move_tag`（`parent_tag_id`の付け替え）と同じ考え方で、移動先が自分自身または自分の子孫でないことを検証する（循環参照の防止）。検証方法は`_assert_no_cycle`のフォルダ版として、再帰CTEで`new_parent_folder_id`の祖先集合を辿り、その中に`folder_id`が含まれないことを確認する。

## 検討した代替案

- **フォルダ名を兄弟内一意（`(parent_folder_id, name)`の複合UNIQUE）にする**: ADR-0072の「タグ名はグローバル一意」という前例に近く、UI上の曖昧さ（同じ親の下に同名フォルダが並ぶ）を防げる。しかし、今回は仕様を最も単純にする方針とし、一意性制約自体を撤廃する案を採用した。将来、UI上の混乱が問題になった場合は、複合UNIQUEへの変更を別途ADRで検討する。
- **子フォルダを持つフォルダの削除を拒否する**（`delete_tag`と同方式）: 実装は単純だが、分類軸の統廃合（浅い階層への整理）のたびに子フォルダを先にすべて手動で移動する必要があり、運用負荷が高いと判断し不採用とした。
- **配下のフォルダを再帰的にカスケード削除する**: 誤操作時に配下フォルダおよびそれらに割り当てられたタグの`folder_id`参照（`ON DELETE`は明示していないため、実際には配下フォルダ削除に伴い`hiroba_tag.folder_id`がNULL化される想定になるが）が広範囲に失われるリスクが大きく、不採用とした。
- **タグの割当を末端フォルダのみに限定する**: 分類の一貫性は高まるが、UI・バリデーションの実装コストが増え、ADR-0072が示した「タグ階層上のどの深さにも付与できる」という設計思想とも整合しないため、不採用とした。

## 結果・影響

- `db_hiroba_qa_init`に、`hiroba_tag_folder.parent_folder_id`列追加・`idx_hiroba_tag_folder_parent_folder_id`インデックス追加・`hiroba_tag_folder_name_key`（UNIQUE制約）撤廃のマイグレーションが追加される（詳細は要件定義書`202609030857`参照）。
- `knowledge_mcp`の`TagRepository`・タグフォルダ関連MCPツール（`list_tag_folders`のツリー化、`create_tag_folder`への`parent_folder_id`パラメータ追加、`move_tag_folder`新設、`delete_tag_folder`の繰り上げロジック追加）に改修が発生する。
- `web_backend`の`/api/tag-folders`エンドポイント、`front_dev`の`TagTreePage.tsx`（フォルダ管理UIのツリー表示・移動操作）・`TagPicker.tsx`・`tagFilter.ts`の`groupTagsByFolder`（ネストしたフォルダのグルーピング表示ロジック）に改修が発生する。
- `search_knowledge`・`QARepository.search`・`qa_tag`・ADR-0058・ADR-0059のロジックには一切変更を加えない。タグフォルダの階層化は`search_knowledge`の検索結果・スコアに影響しない（ADR-0072の方針を継続）。
- `import_tag_batch`/`export_tags`（ADR-0061/0065）・タグフォルダ自体のCSVインポート/エクスポート（ADR-0072が残したOpen Issue #2）は本ADRのスコープでは決定しない。フォルダ階層をCSVで表現する場合の列構成（親フォルダ名またはID列）は、Open Issue #2の結論と合わせて別途検討する。
- 既存タグの`folder_id`・既存フォルダの`name`データはそのまま維持され、`parent_folder_id`は全件`NULL`（ルート直下）として扱われる。
- タグフォルダ名の重複が許容されるため、フロントエンド表示（プルダウン・パンくず等）で同名フォルダが複数表示されうる。利用者が識別しやすいよう、表示上は親フォルダの経路（パンくず）を併記する必要がある（要件定義書6.2節参照）。
