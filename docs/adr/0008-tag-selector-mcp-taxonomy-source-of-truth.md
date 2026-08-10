# ADR-0008: タグ知識ベースの正本を既存 tag テーブルとする（taxonomy.yaml方式は不採用）

- ステータス: Accepted
- 日付: 2026-08-05
- 関連: `docs/requirement/202608051636.md`, `docs/requirement/202608051630.md`, ADR-0005, ADR-0006

## コンテキスト

参照資料（`docs/requirement/202608051630.md`）では、Tag Selector MCP の「Tag Metadata Repository」を `taxonomy.yaml` 等のファイルでタグ（id・name・description・aliases・parent・children・embedding）を管理する案が例示されている。

一方、本プロジェクトでは既に Knowledge MCP サーバの ADR-0005（タグの関連テーブル化）・ADR-0006（タグマスタ管理機能）により、タグは `tag`（自己参照の `parent_tag_id` を持つマスタ）テーブルで管理され、その書き込みは Knowledge MCP のMCPツール（`create_tag` 等）に一元化されている。この既存の正本とは別に `taxonomy.yaml` のような独立ファイルでタグ知識ベースを管理すると、タグ追加・変更のたびに両方を更新する必要が生じ、同期ズレ（Knowledge MCP側でタグをリネームしたのに Tag Selector MCP側のyamlが古いままになる等）のリスクを抱える。

また、現行 `tag` テーブルには `id` / `name` / `parent_tag_id` のみが存在し、Tag Selector MCP が必要とする `description`（説明文）・`alias`（同義語）に相当するカラム・テーブルは存在しない。

## 決定

`taxonomy.yaml` のような独立ファイルは採用せず、**既存 `tag` テーブルを唯一の正本とする**。Tag Selector MCP が必要とする属性を保持するため、以下のスキーマ拡張を行う。

- `tag` テーブルに `description TEXT`（NULL許容）カラムを追加する。
- 同義語は `tag_alias` 関連テーブル（`tag_id` の外部参照、`alias` に一意制約）で表現する（配列カラムは採用しない。理由はADR-0005の考え方を踏襲: 個々の同義語を独立して追加・削除・一意性検証できるようにするため）。

```sql
ALTER TABLE tag ADD COLUMN IF NOT EXISTS description TEXT;

CREATE TABLE IF NOT EXISTS tag_alias (
    id SERIAL PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    alias TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_tag_alias_tag_id ON tag_alias (tag_id);
```

`description` / `tag_alias` の書き込みは、ADR-0006の方針（タグマスタの書き込みはKnowledge MCPのツールに一元化する）を踏襲し、**Knowledge MCP側の既存タグ管理ツール（`create_tag` / `rename_tag` 等）を拡張する形で対応する**。Tag Selector MCP自身は `tag` / `tag_alias` に対して読み取り専用でアクセスする。

## 検討した代替案

- **`taxonomy.yaml` 等の独立ファイルでタグ知識ベースを管理する（参照資料の当初案）**: シンプルで開始しやすいが、既存 `tag` テーブルとの二重管理・同期ズレのリスクが大きく、Knowledge MCPのタグ管理ツールでタグを変更した場合にTag Selector MCP側が追従できないため見送った。
- **Tag Selector MCP が自前で `description` / `alias` を管理する別テーブル・別コンポーネントを持つ**: タグ本体（`tag`テーブル）と付随情報（description/alias）の管理主体が分かれ、タグ削除時の整合性維持（付随情報の削除漏れ等）が煩雑になるため見送った。
- **`tag.aliases TEXT[]` のような配列カラムで同義語を表現する**: 実装はシンプルだが、ADR-0005にて同様の理由（タグ単体の管理・一意性検証のしやすさ）から配列カラム方式を避けた経緯があり、一貫性のため関連テーブル方式を採用した。

## 結果・影響

- Tag Selector MCP は起動時に `tag` / `tag_alias` をロードするだけで、Knowledge MCP側の最新のタグ体系（名称・親子関係・説明文・同義語）を単一の情報源から取得できる。
- Knowledge MCP側のタグ管理ツール（`create_tag` / `rename_tag` 等）を `description` / `alias` の編集にも対応させる拡張が新たに必要になる。この拡張は Knowledge MCP側の変更管理として別途スケジューリングする必要がある（要件定義書 Open Issue #1）。
- 拡張が完了するまでの間は、`description` / `tag_alias` への初期値投入をDBへ直接投入する暫定運用とせざるを得ない。
- 既存の `qa_tag` 検索・タグ書き込みツールの挙動には影響を与えない（カラム・テーブルの追加のみで、既存カラムの変更は伴わない）。
