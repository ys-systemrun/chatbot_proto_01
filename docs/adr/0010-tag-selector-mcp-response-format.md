# ADR-0010: レスポンス形式（選択タグ一覧のみを返し、SearchPlan/階層展開は将来スコープ）

- ステータス: Accepted
- 日付: 2026-08-05
- 関連: `docs/requirement/202608051636.md`, `docs/requirement/202608051630.md`, `docs/requirement/202608041002.md`（Open Issue #8）, ADR-0005, ADR-0009

## コンテキスト

参照資料（`docs/requirement/202608051630.md`）では、Tag Selector MCP がタグ集合ではなく「検索戦略（SearchPlan）」を返す設計が、後続の検索処理との結合度を下げる観点から提案されている。SearchPlanの例には `path`（階層経路）・`weight`（重み）・`expand_children`（子タグを検索対象に含めるか否か）が含まれる。

一方、Knowledge MCP サーバの `search_knowledge` ツールの `tags` フィルタは、ADR-0005および `docs/requirement/202608041002.md` Open Issue #8で確定済みのとおり、**完全一致検索のみ**に限定されており、親タグ指定時に子孫タグを自動展開する機能（`expand_children` に相当する挙動）は実装されていない。また ADR-0009 の決定により、Tag Selector MCP のMVPでも階層構造を用いた探索は行わない。

## 決定

MVPの `select_tags` ツールは、選択されたタグの **`id` / `name` / `score` / `path` の一覧のみ** を返す。

- `path` は将来の階層対応（ADR-0009で見送った階層探索が将来実装された場合）に備え、常に配列型のフィールドとして用意するが、MVP時点ではタグ名1件のみを含む配列とする。
- `weight`・`expand_children` を含む SearchPlan 形式は、本MVPでは採用しない。

## 検討した代替案

- **SearchPlan形式を最初から採用する**: Knowledge MCP側が `expand_children` に相当する階層展開検索に対応していない現状では、`expand_children` を返しても後続処理で利用されず、実質的に機能しないフィールドがインターフェースに残ることになるため見送った。将来 Knowledge MCP側で階層展開検索が実装された時点で、対称的にレスポンス形式を拡張する方が、無駄なフィールドを持たせずに済むと判断した。

## 結果・影響

- Conversation Agent側は、`select_tags` が返すタグ名一覧をそのまま Knowledge MCP の `search_knowledge` の `tags` パラメータへ渡すだけの、シンプルな2段階呼び出しで足りる（要件定義書 5.1節）。
- 将来、Knowledge MCP側で階層展開検索（子孫タグの自動展開）が実装された場合、`select_tags` のレスポンスに `weight` / `expand_children` 等を追加する拡張が必要になる。`path` を配列型としてあらかじめ用意していることで、この際の後方互換性は確保しやすい（既存クライアントは追加フィールドを無視すればよい）。
- 本ADRはKnowledge MCP側の階層展開検索実装状況に依存する決定であるため、Knowledge MCP側の方針変更（Open Issue #8の見直し等）があった場合は本ADRも合わせて見直す必要がある。
