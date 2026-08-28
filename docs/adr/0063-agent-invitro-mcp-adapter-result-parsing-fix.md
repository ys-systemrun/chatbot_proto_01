# ADR-0063: `agent_invitro`のMCPツール戻り値パースを頑健化し、会話タグが常に空になる不具合を修正する

- ステータス: Accepted
- 日付: 2026-08-27
- 関連: `docs/requirement/202608271500_agent_invitroタグ選択結果取得不具合修正要件定義書.md`, `docs/detected_problems/202608270951_チャット情報源検索結果検証ページとの差異調査報告.md`, ADR-0062, ADR-0057, ADR-0059, ADR-0060, ADR-0021

## コンテキスト

実チャット（`agent_invitro`の`POST /ask-sl`）の情報源検索が検証ページと食い違う不具合について、ADR-0062は根本原因を「`agent_invitro/src/tags.py`の`search_with_merged_tags`がタグ別複数回呼び出し＋フォールバック＋最大スコア統合という旧ワークアラウンド（ADR-0057）のまま残っていること」と結論し、検証機能（ADR-0060）と同じ単一`search_knowledge`呼び出し方式へ単純化した。しかしこの変更をAWSへデプロイ後も事象は解消しなかった。

AWS実機（CloudWatch Logs `/ecs/agent_invitro`、ECSタスク定義）を直接確認し、次を特定した。

- **デプロイは正しく反映されている**: `agent_invitro`タスク定義 rev 11 が 2026-08-27 10:20（JST）に登録・ロールアウト完了。環境変数から`TAG_SEARCH_FALLBACK_ENABLED`が削除済み（ADR-0062のterraform変更が適用済み）。イメージも同一apply-app実行内で更新された`:latest`を取得済み。反映漏れではない。
- **デプロイ後（10:28）の実チャット1件のトレース**: `select_tags`呼び出しは`HTTP 200 OK`で成功（例外`select_tags failed`は出ていない）。それにもかかわらず`search_with_merged_tags query='…' merged_tags=0 hits=1`、すなわち**マージタグ0件**で検索が走っている。
- **デプロイ前（09:15台）のログも一貫して`merged_tags=0`**。

したがって、実チャットのタグ選択（`select_tags`結果 → 会話タグ化）は**本機能のリリース以来一度も機能しておらず、常にタグなしの埋め込み類似度検索のみ**で動作していた。ADR-0059により「`tags`未指定（`tags=None`）と空配列（`tags=[]`）は同一扱い」であるため、マージタグが常に空である以上、旧コード（フォールバック1回）と新コード（`tags=[]`1回）は同じ結果になる。**ADR-0062の単純化は報告事象の是正には寄与しておらず、真因の診断が誤っていた**（レイテンシ削減という副次効果はある）。

真因は`agent_invitro`の受信・パース層にある。`agent_invitro`は`langchain-mcp-adapters`（ADR-0021）でMCPサーバーへ接続し、戻り値を2つのアドホックな抽出関数でパースしている。

- `_extract_selected_tags`（tags.py）: dict / JSON文字列 / bytes / tuple のみ対応し、`langchain-mcp-adapters`が返す**テキストブロックのlist形式**（例: `[{"type":"text","text":"<json>"}]`）に非対応。list を受け取ると無言で`[]`を返す → `new_tags`が常に空 → `merged_tags`が常に0。
- `_extract_results`（server.py）: list 分岐は持つが、テキストブロックの`text`をJSONとして解釈しないため、本来の`results`ではなくブロックそのものを返している疑いが強い（`hits`が観測上つねに1であることと整合）。この場合、検索側も有効なコンテキストを生成できていない。

対照的に、正しく動作している検証ページ（`web_backend`）は`langchain-mcp-adapters`を使わず、独自クライアントで`CallToolResult.structuredContent`（`{"selected": [...]}` / `{"results": [...]}`）を直接読む。差はこの取得（パース）層の実装差にある。`tag_selector_mcp`・`knowledge_mcp`（サーバー側）は`structuredContent`を含む正しいMCPレスポンスを返しており、サーバー側に問題はない。

## 決定

**`agent_invitro`のMCPツール戻り値パースを、`langchain-mcp-adapters`が返し得る全形式に対して頑健化する。** 対象は`_extract_selected_tags`（tags.py）と`_extract_results`（server.py）の両方とする。

- 両抽出関数が共通で使える「MCPツール戻り値 → payload(dict)正規化」処理を設け、少なくとも次を処理する: dict（structuredContent相当）／`(content, artifact)`タプル／bytes／JSON文字列／**テキストブロックのlist**（各ブロックの`text`または要素自身のJSON文字列を`json.loads`し、目的キーを含むdictを取り出す）。`_extract_selected_tags`は`selected`、`_extract_results`は`results`を取り出す。
- 目的の配列を取り出せず結果が空になった場合は、`WARNING`で戻り値の`type`名と先頭一定文字数を診断ログ出力する。想定外形式が返っても次回以降のログから形式を確定して追加対応できるようにする。
- ADR-0062で確定した単一`search_knowledge`呼び出し方式、および継続タグ判定ロジック（ADR-0057 4節）は変更しない。本ADRはパース層のみを修正する。
- 是正はAWS実機のCloudWatch Logsで`merged_tags>0`かつ`hits`が実QA件数を反映することにより確認する。

## 検討した代替案

- **`_extract_selected_tags`だけを修正する**: 却下。`_extract_results`も同種の欠陥（テキストブロックの`text`を解釈しない）を持ち、検索側でも有効なコンテキストを生成できていない疑いが強い。タグを直しても情報源本文が空のままでは目的（検証ページと同等の情報源取得）を達成できないため、両者を修正する。
- **`langchain-mcp-adapters`から独自MCPクライアント（検証ページ方式）へ全面移行する**: 却下（本ADRのスコープでは）。`structuredContent`を直接読む方式は堅牢で最終的には望ましいが、`agent_invitro`のツール取得・呼び出し全体（`build_mcp_client`/`load_tools`/`search_with_merged_tags`等）の作り替えを伴い影響範囲が大きい。まずは低リスクなパース頑健化で事象を止め、クライアント一本化は要件定義書8章 Open Issue #1として別途判断する。
- **`langchain-mcp-adapters`のバージョンを、戻り値が予測可能な版に固定する**: 却下。特定バージョンへの依存はもろく、ライブラリ更新のたびに再発し得る。形式差を吸収する頑健なパースの方が本質的で保守的。
- **ADR-0062を差し戻す（タグ別複数回呼び出し方式へ戻す）**: 却下。ADR-0062の単一呼び出し化は検証ページと方式を揃える正しい方向であり、レイテンシ面でも優れる。真因はパース層にあり、呼び出し方式とは独立しているため、差し戻す理由はない。

## 結果・影響

- `agent_invitro/src/tags.py`・`agent_invitro/src/main/api/server.py`のパース処理が、`langchain-mcp-adapters`のテキストブロックlist形式を含む全戻り値形式に対応する。会話タグが質問に応じて正しく付与され、実チャットの情報源検索が検証ページと整合するようになる。
- 戻り値パース失敗時の診断ログにより、将来ライブラリ更新等で想定外形式が返っても早期に検知・対応できる。
- `agent_invitro/tests`に、各戻り値形式（特にテキストブロックのlist）に対する抽出関数のユニットテストを追加する。
- ADR-0062の決定（単一`search_knowledge`呼び出し方式）は維持する。ただしADR-0062が記した「報告事象の根本原因＝呼び出し方式の世代差」という診断は誤りであり、真因は本ADRのパース層の欠陥であったことを、ADR-0062へ補足する（差し戻しは行わない）。
- `docs/detected_problems/202608270951_...`の根本原因（4章）は、本ADRにより「呼び出し方式の世代差」から「MCPアダプタ戻り値のパース欠陥（会話タグが常に空）」へ更新される。
- 独自MCPクライアントへの一本化、`top_k`・`min_score`の値統一、実チャットUIへの情報源表示は、本ADRのスコープ外の未決事項として要件定義書8章 Open Issueに記録済みであり、別途判断する。
