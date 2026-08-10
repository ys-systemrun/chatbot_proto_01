# ADR-0004: MVPスコープ（QA JSON Adapterのみ初回実装）

- ステータス: Accepted
- 日付: 2026-08-04
- 関連: `docs/requirement/202608041002.md`

## コンテキスト

参照資料（`docs/requirement/202608040945.md`）では、QA / マニュアル / PDF / API / DB 等、複数データソースに対応する Repository 構成が将来像として示されている。初回リリースでどこまでの範囲を実装するか検討した。

## 決定

初回リリース（MVP）では **QA JSON（既存 `data/exportjson_withguid.json` 相当のデータ）を扱う QARepository のみを実装する**。他の Repository（PDF / マニュアル / API 等）は Repository 抽象（インターフェース）としてのみ設計し、実装は将来のスコープとする。

## 検討した代替案

- **参照資料に記載の全Adapter（QA/PDF/Manual/API/DB）を初回実装する**: 開発・検証コストが大きく、既存機能（現行 `search_similar` 相当）の置き換えというMVPの目的に対して過剰スコープと判断し見送った。

## 結果・影響

- 実装・検証範囲が既存機能の置き換えに閉じるため、リリースまでの期間を短縮できる。
- Repository 抽象を最初から用意することで、将来 PDF / マニュアル / API Adapter を追加する際に `SearchService` および `search_knowledge` ツール側の変更を最小限にできる。
- タグ推定・カテゴリ推定等、複数ソース横断のクエリ最適化（Query Analyzer / Repository Selector 相当の機能）の本格的な効果検証は次フェーズ以降になる。
- 将来 Repository の優先順位・着手時期は Open Issue として要件定義書に記載している。
