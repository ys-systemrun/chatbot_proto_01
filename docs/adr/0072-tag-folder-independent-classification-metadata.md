# ADR-0072: タグフォルダ（タグの分類表示専用メタデータ）の新設

- ステータス: Accepted
- 日付: 2026-09-02
- 関連: `docs/requirement/202609021050_タグ運用ガイドライン.md`、`docs/requirement/202609021102_タグ管理画面・タグ選択UI改修要件定義書.md`、ADR-0005、ADR-0006、ADR-0058、ADR-0059

## コンテキスト

タグ運用ガイドライン（202609021050）は、タグの分類軸（「文脈」「話題」等）が事前に完全には確定できず、運用しながら軸の種類が増減しうること、また同じタグが場面によって軸の役割を変える相対的な性質を持つことを整理した上で、「タグ階層（`parent_tag_id`）は本当のis-a関係にのみ使い、独立した2軸の組み合わせは階層化せずQA側の組み合わせタグ付けで表現する」という方針を示した（ガイドライン3章）。

この方針のもとでは、タグを分類軸ごとに見渡すための`parent_tag_id`によるis-a階層とは別の手がかりが管理画面上に存在しないため、担当者がどのタグがどの軸に属するかを把握しづらいという課題が残る。タグ運用ガイドライン検討時には、既存の`parent_tag_id`ツリーの最上位階層を分類軸（フォルダ）として転用する案も検討されたが、この場合`parent_tag_id`が持つ検索上の意味（ADR-0058の祖先タグ展開、ADR-0059のタグ構成類似度計算）に、本来検索的な意味を持たないはずの分類軸ノードが混入してしまう副作用が指摘されていた。

## 決定

**タグに、`parent_tag_id`によるis-a階層とは完全に独立した「タグフォルダ」というメタデータ属性を新設する。タグフォルダは管理画面・選択UIの表示（グルーピング）専用の属性とし、`search_knowledge`の検索ロジック（ADR-0058の祖先タグ展開、ADR-0059のタグ構成類似度計算）には一切使用しない。**

データモデルは、既存の`tag_alias`と同様の「独立したマスタテーブル＋外部キー」方式とする。

```sql
CREATE TABLE IF NOT EXISTS hiroba_tag_folder (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

ALTER TABLE hiroba_tag
    ADD COLUMN IF NOT EXISTS folder_id INTEGER REFERENCES hiroba_tag_folder(id);

CREATE INDEX IF NOT EXISTS idx_hiroba_tag_folder_id ON hiroba_tag (folder_id);
```

- 1タグにつきタグフォルダは0または1件（`folder_id`はNULL許容）とする。
- タグフォルダは`parent_tag_id`による階層上のどの深さのタグにも付与できる（タグフォルダへの割当とis-a階層上の位置は無関係）。
- タグフォルダマスタの管理は、`tag_alias`と同様に`knowledge_mcp`のMCPツール（`list_tag_folders`/`create_tag_folder`/`rename_tag_folder`/`delete_tag_folder`）として提供する。`delete_tag_folder`は、`hiroba_tag`から参照されているタグフォルダの削除を拒否する（既存の`delete_tag`と同じ考え方）。
- `create_tag`/`rename_tag`（またはこれに相当する更新系ツール）に`folder_id`パラメータを追加し、タグへのタグフォルダ付与・変更・解除ができるようにする。

## 検討した代替案

- **既存の`parent_tag_id`ツリーの最上位階層を分類軸（フォルダ）として運用する（スキーマ変更なし）**: 実装コストが最小で済む利点があるが、`parent_tag_id`に基づくADR-0058の祖先タグ展開・ADR-0059のタグ構成類似度計算に、分類目的でしかない最上位ノードが検索上の意味を持つものとして混入してしまう。たとえば「文脈」という分類目的の最上位タグの下に「A」を置くと、QAに「A」を付けた時点でそのQAは検索上「文脈」タグでも見つかることになり、タグ構成類似度のJaccard係数の分母・分子にも意味を持たない分類ノードが混入する。この副作用はタグ運用ガイドライン検討時に既に指摘されており、この案は採用しなかった。
- **`hiroba_tag`に`folder`列をTEXT型で直接持たせる（マスタテーブルを設けない）**: 実装は単純だが、タグ名自体と同様に表記ゆれ・重複が発生しうる（本ADRが解決しようとしている「文脈」「話題」等の分類軸の一貫性の問題が、フォルダ名自体で再発する）。既存の`tag_alias`が独立したマスタテーブルで一意性を管理する方式を踏襲し、`hiroba_tag_folder`という独立したマスタで一意性（`name UNIQUE`）を保証する方式を採用した。
- **1タグが複数のタグフォルダに属することを許容する（多対多）**: 「認証」が「機能」でもあり「文脈」の一部でもある、といったケースに対応できる柔軟性があるが、実際にそのようなニーズが確認できていない段階で多対多の関連テーブル（`tag_folder_assignment`）を導入するのは過剰設計と判断し、MVPでは単純な0/1件の`folder_id`に留めた。将来ニーズが具体化した場合は関連テーブル化で拡張できる（結果・影響参照）。

## 結果・影響

- `db_hiroba_qa_init`に、`hiroba_tag_folder`テーブルの新設・`hiroba_tag.folder_id`列追加のマイグレーションが追加される。既存タグは`folder_id = NULL`（未分類）として扱われる。
- `knowledge_mcp`の`TagRepository`・`TagNode`（モデル）、`web_backend`の`tag_controller.py`（`/api/tag-folders`エンドポイント新設）、`front_dev`の`TagPicker.tsx`／`TagTreePage.tsx`／`domain/admin/tag.ts`に、タグフォルダの読み書き・グルーピング表示のための改修が発生する（詳細は要件定義書202609021102参照）。
- `tag_selector_mcp`の`TagMetadataRepository`は`hiroba_tag`を明示的な列指定で読み込む実装のため、`folder_id`列の追加によって自動的に取り込まれることはなく、無改修で動作を継続する。
- `QARepository.search`・`qa_tag`・ADR-0058・ADR-0059のロジックには一切変更を加えない。タグフォルダの設定・変更は`search_knowledge`の検索結果・スコアに影響しない。
- `import_tag_batch`/`export_tags`（ADR-0061/0065）の列構成にタグフォルダを含めるかどうかは、本ADRのスコープでは決定しない別途の検討事項とする（要件定義書202609021102 Open Issue #2）。含めない場合、CSV経由で作成・更新されたタグのタグフォルダは管理画面上で個別に設定する運用になる。
- タグフォルダマスタの作成・削除権限は、ADR-0006が残したタグ管理全般の権限に関するOpen Issueと同じ論点であり、本ADRでは決定しない（タグ運用ガイドライン9章参照）。
