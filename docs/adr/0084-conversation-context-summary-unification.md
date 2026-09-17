# ADR-0084: 会話文脈管理の一本化（会話タグ機構の廃止、summary方式への統合）

- ステータス: Accepted
- 日付: 2026-09-09
- 関連: `docs/requirement/202609091730_タグ選定・会話文脈管理再設計要件定義書.md`, ADR-0043, ADR-0056, ADR-0057, ADR-0085, ADR-0086

## コンテキスト

`agent_invitro`には、会話の文脈を圧縮して次ターンへ持ち回す仕組みが2系統存在していた。

1. **`summary`（会話要約）**: ADR-0043以前から存在する仕組み。`messages`が15件を超えると古い3件をLLMで3文程度に要約し、`summary.content`として保持する。クライアントエコー方式（サーバー側DB非永続化、`Response.summary`をクライアントが保持し次回`Request.summary`で送り返す）で、`generator.generate()`の回答生成コンテキストとしてのみ使われる。
2. **会話タグ**（ADR-0056/0057）: `summary`と「同一の設計思想（クライアントエコー方式）」を踏襲して後から追加された仕組み。`select_tags`の結果とクライアント由来のタグを`missed_turns`（連続で再選択されなかったターン数）により継続判定し、`search_knowledge`の`tags`引数としてのみ使われる。

発注者との協議の結果、「タグ」という仕組みには（a）会話文脈の管理、（b）検索のための表記ゆれ正規化、（c）QA・記事間の構造化、という3つの異なる責務が同居しており、（a）は本来`summary`が担うべき責務であるにもかかわらず、静的なタクソノミーの語彙（`tag_id`・タグ名）を借用してセッションローカルな動的状態（`missed_turns`による減衰）を表現する形で会話タグ側に重複して実装されていたことが判明した（REQ-202609091730 2.2節）。

これとは別に、REQ-202609091730・ADR-0085・ADR-0086により、`select_tags`の呼び出し方自体を「その場（要約＋未要約履歴＋今回の発話から言い換えた質問）から毎ターン新たにタグを求める」方式へ変更することが決定した。この新方式では、`select_tags`の入力自体に文脈（要約・未要約履歴）が反映されるため、会話タグ側が担っていた「ターンをまたいだタグの継続」という役割は不要になる。

## 決定

**会話タグ機構（ADR-0056/0057）を廃止する。会話文脈の管理は`summary`（会話要約）に一本化する。`Request`/`Response`契約から`tags`（`ConversationTag`）フィールドを削除する。**

1. **`front_dev`**: `StateContainer.tsx`の`tags: ConversationTag[]`React state、および`domain/stateless/{request,response}.ts`の`ConversationTag`型・`Request.tags`/`Response.tags`を削除する。
2. **`web_backend`**: `main/controllers/chat_controller.py`の`Request`/`Response`Pydanticモデルから`tags`フィールドを削除する。AWS環境向け中継処理（`AGENT_INVITRO_URL`設定時のパススルー）も、このフィールドを扱わなくなる。
3. **`agent_invitro`**: `main/api/server.py`の`Request`/`Response`モデルから`tags`フィールドを削除する。`tags.py`から`TagState`データクラス・`compute_conversation_tags()`（継続判定ロジック）を削除する。`_extract_selected_tags()`/`_mcp_result_to_dicts()`（langchain-mcp-adaptersの戻り値正規化ヘルパー、ADR-0063由来）は`select_tags`の呼び出しに引き続き必要なため残す。`search_with_merged_tags()`は、ADR-0086の新フローにおける「その場で得たタグ集合をそのまま`search_knowledge`へ渡す」処理へ置き換える（クライアント由来タグとのマージは行わない）。

会話文脈の管理は`summary`（既存の要約LLM呼び出し、`summarize.py`）にすべて委ねる。会話タグが担っていた「今何の話をしているか」という状態は、ADR-0085が新設する言い換え質問（`condensed_query`）が要約・未要約履歴を踏まえて毎ターン生成することで代替する。

## 検討した代替案

- **会話タグ機構を維持し、ADR-0085/0086の新フローと並走させる**: 移行リスクを避けられる利点はあるが、（1）`missed_turns`による継続判定は「その場で文脈込みのタグを求め直す」新フローと役割が完全に重複し、二重管理になる、（2）2つの仕組みが同時に`search_knowledge`のタグ選定に影響すると、どちらの判定が優先されたか運用上追跡しづらくなる、という理由から不採用とした。発注者からも「廃止して一本化する」との明確な回答を得た。
- **段階的移行（まず新フローを追加し、安定を確認してから会話タグを廃止する）**: 安全な移行ではあるが、（a）本ADRの決定自体は「廃止する」という最終形が既に確定していること、（b）会話タグを一時的に残すコストに対して得られる安全性が限定的であること（`front_dev`/`web_backend`/`agent_invitro`いずれも変更は局所的で、ロールバックはgit revertで容易）から、一括での廃止を採用した。実装フェーズでのリリース順序については、REQ-202609091730 14章の通りADR-0086・ADR-0085を先行させ、動作確認後に本ADRの変更を適用する。
- **`summary`側に構造化情報（タグ相当のラベル）を持たせ、会話タグのデータ構造自体は残しつつ生成方法だけを変える**: `summary`は自由文であり、`search_knowledge`の`tags`引数（タグ名の配列）として使うには別途パースが必要になり、かえって複雑になる。`select_tags`を毎ターン呼び出せば構造化されたタグ配列がそのまま得られるため、この代替案は不採用とした。

## 結果・影響

- `front_dev`・`web_backend`・`agent_invitro`の3層から会話タグ関連のコード・スキーマフィールドが削除される。`knowledge_mcp`・`tag_selector_mcp`自体への影響はない（呼び出し方が変わるのみ、ADR-0085/0086で詳述）。
- `ConversationTag`型・`missed_turns`という概念そのものが本プロジェクトから消滅する。将来的にタグの継続性に基づく別の要件（例:「一度確定したタグを一定ターン数保持したい」）が生じた場合は、`summary`とは別に改めて設計する必要がある。
- ADR-0056・ADR-0057は本ADRにより廃止される。両ADRのステータス行に、本ADRによる廃止の旨を追記する（プロジェクトの慣例、ADR-0057自身のステータス行がADR-0062による改訂を注記している前例に倣う）。
- `agent_invitro/src/main/api/server.py`のコメント「### ↓この辺をもう少しAgenticに？」が示唆する、固定シーケンス（`select_tags`→`search_knowledge`→`generate`）自体の見直しは本ADRの対象外とする。
