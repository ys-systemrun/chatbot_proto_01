# docs/ — 設計・開発ドキュメント

chatbot_invitro の要件定義書・ADR・実装指示書・調査報告・画面遷移図・構成図・開発サマリなど、コード以外の設計資料をまとめるフォルダです。
おおまかな流れは「要件定義書（`requirement/`）→ ADR（`adr/`）→ 実装指示書（`implementation_handoff/`）」で、運用中に見つかった問題は `detected_problems/`、回答品質の改善記録は `improvements/` に残します。

## 構成

| 名前 | 説明 |
|---|---|
| [`2026-08-summary/`](2026-08-summary/README.md) | 2026年8月（08-04〜08-27）の開発サマリ。HTML 版と Marp スライド版 |
| [`2026-08-summary_02/`](2026-08-summary_02/README.md) | 2026年8月の開発サマリの改訂版（期間を 09-04 まで延長し 5 フェーズ構成にしたもの） |
| [`2026-09-summary/`](2026-09-summary/README.md) | 2026年9月（09-08〜09-28）の開発サマリ（HTML） |
| [`2026-09-summary_02/`](2026-09-summary_02/README.md) | 2026年9月〜10月初旬（09-08〜10-05）の開発サマリの改訂版（7 テーマ構成） |
| [`2026-10-summary/`](2026-10-summary/README.md) | 2026年10月（10-05〜10-26）の開発サマリ（改善ループ・評価基盤など） |
| [`adr/`](adr/README.md) | ADR（Architecture Decision Records）。設計判断を 1 件 1 ファイルで記録し、README が索引 |
| [`detected_problems/`](detected_problems/README.md) | 運用・検証中に検出された問題の調査報告 |
| [`implementation_handoff/`](implementation_handoff/README.md) | 要件定義書・ADR を実装着手できる粒度まで具体化した実装指示書 |
| [`improvements/`](improvements/README.md) | 回答品質の改善ループ（ADR-0099）で行った改善の記録とテンプレート |
| [`network_diagram/`](network_diagram/README.md) | 検証環境（AWS）のネットワーク構成図（mingrammer/diagrams による Diagram as Code）と生成スクリプト |
| [`requirement/`](requirement/README.md) | 機能ごとの要件定義書・構成検討メモ・運用ガイドライン |
| [`screen_transition/`](screen_transition/README.md) | front_dev（SPA）の画面遷移図と画面スクリーンショット |
