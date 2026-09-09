# ADR-0080: タグエイリアスの追加・編集・削除機能の実装方式（update_tag_alias新設、既存タグCRUDと同一の権限・ログ方針を踏襲）

- ステータス: Accepted
- 日付: 2026-09-09
- 関連: `docs/requirement/202609091119_タグエイリアス管理機能要件定義書.md`, ADR-0006, ADR-0008, ADR-0013

## コンテキスト

ADR-0006により、Knowledge MCPに`add_tag_alias`/`remove_tag_alias`が追加されていたが、`web_backend`の`/api/tags`（`tag_controller.py`）はこれらを呼び出すエンドポイントを持たず、`front_dev`の`TagTreePage`もエイリアスを表示専用（`title="同義語（表示のみ）"`）としてしか扱っていなかった。加えて、エイリアス文字列自体を書き換える更新系ツールはそもそも存在しない。この結果、タグ運用ガイドライン（202609021050）が前提とする「表記ゆれをエイリアスとして追加する」「統合時に片方をエイリアスとして残す」という運用を、担当者が管理画面から実行する手段がなかった。

発注者確認の結果、次の方針で機能を追加することとした。

- 「編集」は、既存の`add_tag_alias`/`remove_tag_alias`の組み合わせ（削除して別文字列を追加）ではなく、`update_tag_alias`という新規ツールを追加してその場で書き換えられるようにする。
- 権限制御・監査ログは、既存のタグCRUD（`create_tag`/`rename_tag`等）と同じ扱い（権限制御なし、`log_admin_operation`による操作ログ記録のみ）を踏襲する。

## 決定

**Knowledge MCPに`update_tag_alias(alias_id, new_alias)`を新設し、`web_backend`の`tag_controller.py`に、既存の`create_tag`/`update_tag`と同じパターン（MCPツール呼び出し＋`log_admin_operation`記録のみの薄いBFF、ADR-0013）でエイリアス操作を仲介する処理を追加する。`front_dev`の`TagTreePage`には、タグ行のエイリアス表示に追加・編集・削除の操作を追加する。**

- **`update_tag_alias`の新設**: `TagRepository.update_tag_alias(alias_id, new_alias)`は、対象`alias_id`の存在チェック、`new_alias`が自分自身以外の既存エイリアスと重複していないかのチェック（`add_tag_alias`と同じUNIQUE制約由来の`TagError`）を行った上で`UPDATE tag_alias SET alias = %s WHERE id = %s`を実行する。既存の`add_tag_alias`/`remove_tag_alias`のシグネチャ・実装は変更しない。
- **web_backend**: `tag_controller.py`に、`add_tag_alias`/`update_tag_alias`/`remove_tag_alias`をそれぞれ呼び出す関数を追加し、既存の`create_tag`/`update_tag`/`delete_tag`と同じく処理の末尾で`log_admin_operation("create"|"update"|"delete", "tag_alias", alias_id, ...)`を記録する。エンドポイントのURLは`/api/tags/{tag_id}/aliases`（POST）・`/api/tags/{tag_id}/aliases/{alias_id}`（PUT/DELETE）とし、`tag_id`はUI上の文脈を表すパス要素として使うのみで、`update_tag_alias`/`remove_tag_alias`自体の引数には使わない（`alias_id`だけで一意に解決できるため）。
- **front_dev**: `TagTreePage.tsx`のタグ行にあるエイリアス表示（`node.aliases.map(...)`）を、表示専用のバッジから、追加用の入力欄＋ボタン、各バッジのクリックによる編集（インライン編集または`window.prompt`相当の簡易UI。既存の`rename_tag`のUIと同水準）、削除ボタンを備えたUIに変更する。
- **権限・監査ログ**: 新設するエイリアス操作にも、既存のタグCRUDと同じく権限制御は設けず、`log_admin_operation`による操作ログの記録のみを行う。ADR-0006が残した「タグ管理全般の権限」Open Issueは、本ADRでも据え置く（発注者確認済み）。

## 検討した代替案

- **`update_tag_alias`を新設せず、UI側で「削除→追加」の2操作として編集を実現する**: バックエンドの変更（新規ツール・新規エンドポイント）を最小限にできる利点はあるが、（1）`alias_id`が変わってしまうため、当該エイリアスを参照する将来の機能（例: どのエイリアス経由でヒットしたかのログ等）にとって不透明な挙動になる、（2）削除と追加の間に一瞬でもエイリアスが存在しない状態が生じ、同時実行時の一貫性が損なわれる、という理由から不採用とした。発注者確認の結果、素直に更新系ツールを新設する方針を選んだ。
- **エイリアス操作専用の権限・承認フローを新設する**: タグ運用ガイドライン（202609021050）はタグ管理全般の慎重な運用を求めているが、エイリアス操作だけを特別扱いする理由は薄く、ADR-0006が既に「タグ管理全般の権限」を未解決のOpen Issueとして許容している現状の運用と一貫性を保つため、既存のタグCRUDと同じ（権限制御なしでログのみ）扱いを踏襲することとした（発注者確認済み）。
- **タグ管理全般の権限モデルをこの機会にあわせて検討する**: スコープが大きく広がり、本来の目的（エイリアスCRUDの実現）から外れるため見送った。ADR-0006のOpen Issueとして引き続き別途検討する。

## 結果・影響

- `knowledge_mcp`に`update_tag_alias`とその実装（`TagRepository`への新規メソッド）が追加される。既存の`add_tag_alias`/`remove_tag_alias`/`list_tags`等の実装・シグネチャには変更を加えない。
- `web_backend`の`tag_controller.py`にエイリアス操作用の関数・エンドポイントが追加される。既存のタグ・タグフォルダ関連エンドポイントには変更を加えない。
- `front_dev`の`TagTreePage`にエイリアスの追加・編集・削除UIが追加される。既存の検索絞り込み（ADR-0070）・類似候補チェック（ADR-0071、ADR-0082で拡張）とは独立して動作する。
- タグ管理全般の権限・承認フローは引き続き未整備のまま（ADR-0006のOpen Issue）であり、エイリアス操作もその対象に含まれる。
