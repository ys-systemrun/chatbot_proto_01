# ADR-0015: front_dev管理画面のルーティング方式（react-router-domを管理画面サブツリーに限定導入）

- ステータス: Accepted
- 日付: 2026-08-06
- 関連: `docs/requirement/202608060826.md`

## コンテキスト

現行 `front_dev` は、`main.tsx` が `window.location.pathname` を厳密一致で判定し、3つのエントリ（`App` / `AppStateless` / `AppEvaluatedMessages`）のいずれかをマウントするだけの単純な構成であり、ルーティングライブラリ（React Router 等）は導入されていない。

`docs/requirement/202608060826.md` で追加するQA一覧・タグ階層・QA登録編集・タグ登録編集の各ページは、以下の理由から、既存の「pathname完全一致で固定ページを1つ選ぶ」方式では対応が難しい。

- QA編集・タグ編集は対象データの `id` を含む動的なURL（例: `/admin/qa/{id}`）が必要になる。
- 一覧ページから編集ページへの遷移、保存後の一覧への戻り等、ページ間の遷移が既存3画面より多い。

## 決定

新設する管理画面機能（QA一覧・タグ階層・登録編集フォーム）に限定して `react-router-dom` を導入する。`main.tsx` の既存pathname分岐に、新たなプレフィックス `/admin` を追加し、パスが `/admin` から始まる場合は新設する `AppAdmin` エントリをマウントする。`AppAdmin` の内部では `react-router-dom` によるルーティング（`/admin/qa`, `/admin/qa/:id`, `/admin/qa/new`, `/admin/tags` 等）を行う。既存の `App` / `AppStateless` / `AppEvaluatedMessages` の3画面と、それらのpathname分岐方式自体は変更しない。

## 検討した代替案

- **既存同様、pathname完全一致とクエリパラメータの組み合わせのみで対応する方式**（例: `/admin_qa_edit?id=xxx` のような固定パス＋クエリパラメータ）: 既存パターンを踏襲でき新規依存も不要だが、ページ数・遷移パターンの増加に伴い `main.tsx` の分岐やページ間遷移の実装（`window.location` の書き換え等）が煩雑化し、ブラウザの戻る/進む・ブックマークとの整合性も損なわれるため見送った。
- **`front_dev` 全体を `react-router-dom` ベースへ移行する方式**: 既存チャットデバッグ3画面への影響範囲が大きく、本フェーズのスコープ（管理機能の追加）を超えるため見送った。将来的な全面移行の可能性は残すが、本ADRの対象外とする。

## 結果・影響

- `front_dev` の依存パッケージに `react-router-dom`（および必要な型定義）が追加される。
- 既存3画面（チャット・ステートレス版・評価済みメッセージ）のURL・実装・動作は変更されない。
- Vite dev server の設定（`vite.config.ts`）において、新規追加するAPIパスを `/api` 配下に統一したことで（要件定義書9.2節）、`/admin` 配下のページパスとAPIパスが重複せず、既存 `/evaluated_messages` で必要だった「HTMLリクエストか否かで振り分けるbypass設定」のような特別な分岐は不要となる。
- 将来 `front_dev` 全体をルーティングライブラリへ統一する場合、本ADRで実装する `AppAdmin` の構成を土台として拡張できる。
