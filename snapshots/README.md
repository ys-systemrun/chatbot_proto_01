# snapshots/ — 復旧専用のデータ（DVC 管理）

DB を戻すためだけに使うデータを置きます（ADR-0109）。シードには使わず、db_init のイメージにも入りません。
中身は DVC で管理し、git に入っているのは `.dvc`（内容ハッシュ）とこの README だけです。
取得は `terraform\dvc.bat pull`、記録は `dvc add` → `.dvc` をコミット → `terraform\dvc.bat push`。

| 名前 | `.dvc` | 内容 |
|---|---|---|
| `conversation/` | `conversation.dvc` | conversation DB（会話・評価・検証）のスナップショット。テーブルごとの CSV（PostgreSQL の COPY 形式, 埋め込みなし）と `manifest.json`。`kb-export.bat` が書き出す。シードでは戻らない（新しい環境の conversation DB は空）ので、新しい環境では `kb-import.bat --target conversation` で戻してから書き出す。**利用者の会話を含むため、CSV を git やチャットに貼らない** |
| `legacy_sql/2026-10-26/` | `legacy_sql.dvc` | 2026-10-26 に AWS から `export-data` で退避した SQL（`knowledge.sql` / `conversation.sql` / `manifest.json`）。AWS の DB を破棄したため、これが当時の本番データの原本。CSV スナップショットから DB を戻せることを確かめるまでの保険として残す（ADR-0109 段階 5 で削除する） |

knowledge DB のスナップショットは、シード元データを兼ねるため `db_init/data/knowledge/` にあります。
