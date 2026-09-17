# ADR-0085: 質問の言い換え（Query Condensation）ステップの新設

- ステータス: Accepted
- 日付: 2026-09-09
- 関連: `docs/requirement/202609091730_タグ選定・会話文脈管理再設計要件定義書.md`, ADR-0043, ADR-0084, ADR-0086

## コンテキスト

現状`agent_invitro`の`_ask_impl`は、`select_tags`にも`search_knowledge`にも`query=req.text`（今回の発話そのもの）しか渡していない。そのため「認証がうまくいきません→ネットワーク認証です→XXXという条件です」のような、複数ターンにまたがる文脈依存の短い発話（「XXXという条件です」単体）では、タグ選定・情報源検索のいずれも文脈を踏まえられない。

ADR-0084により会話タグ機構（ターンをまたいだタグの継続判定）を廃止し、会話文脈の管理を`summary`に一本化する方針が決定した。この場合、`select_tags`側で文脈を踏まえるためには、`summary`・未要約履歴・今回の発話を`select_tags`/`search_knowledge`の入力自体に反映する必要がある。

これを実現する方式として、（a）要約・履歴・発話を生のテキストとして連結する方式と、（b）LLMにより文脈を踏まえて今回の発話を単体で意味が通る質問文（standalone question）へ言い換える方式、の2案を検討した。（a）は`select_tags`のプロンプト（ADR-0009により既に全タグ一覧を含む）がターンを追うごとに際限なく肥大化し、レイテンシ・コストが悪化する懸念があり、また`search_knowledge`の埋め込みベクトルも過去の話題の語彙で薄まり検索精度が落ちる懸念がある。発注者との協議の結果、（b）の言い換えステップを挟む方針で合意した。

## 決定

**`agent_invitro`に、`summary.content`・未要約履歴・`req.text`から、standaloneな言い換え質問（`condensed_query`）を生成するLLM呼び出しを新設する。`condensed_query`は`select_tags`の`query`と`search_knowledge`の`query`の両方に使う。**

1. **入力**: `summary.content`（既存の要約）、未要約履歴（`[m for m in messages if m.order > summary.summarized_upto]`の`role`・`content`）、`req.text`（今回の発話）。
2. **出力**: 単体で意味が通る、standaloneな日本語の質問文1件（余分な前置き・説明を含まない、`summarize.py`の`_SYSTEM_PROMPT`と同様の出力制約を課す）。
3. **実装配置**: `agent_invitro/src/summarize.py`と同型の構成（Bedrock `converse` API呼び出し、プロンプト定数を自己完結で保持する新規モジュール、例:`condense.py`）を踏襲する。`agent_invitro`を`web_backend`から独立させる既存方針（`summarize.py`冒頭コメント参照）と一貫させる。
4. **失敗時のフォールバック**: LLM呼び出しが例外を送出した場合、または未要約履歴・要約のいずれも存在しない場合（会話の最初のターン）は、`req.text`をそのまま`condensed_query`として使う。`summarize.py`の`summarize()`が失敗時に既存`summary`を返す方針と同じ考え方である。
5. **`_ask_impl`内の呼び出し順序**: `summary`更新処理（15件超の要約畳み込み）の後、`select_tags`呼び出しの前に本ステップを実行する。`condensed_query`は`select_tags`の`query`と`search_knowledge`の`query`の両方に同一の値を使う（挙動の一貫性のため。7章参照）。

## 検討した代替案

- **要約・履歴・発話を生のテキストとして連結し、`select_tags`/`search_knowledge`にそのまま渡す**: 実装コストが最小である利点はあるが、コンテキストに引きずられているのは全体構成ではなく「今回の発話が指している対象は何か」という一点であるため、ターンを追うごとにプロンプト・埋め込みベクトルへ不要な語彙が蓄積し、`select_tags`のレイテンシ・コスト増、`search_knowledge`の検索精度低下という2つの副作用を招く。発注者確認の結果、言い換えステップを挟む方式を採用した。
- **`select_tags`と`search_knowledge`で異なるテキストを使う（例:`select_tags`は生の連結、`search_knowledge`は言い換え後）**: 実装の一貫性が失われ、挙動の予測が難しくなる。両者に同一の`condensed_query`を使うことで、「タグ選定」と「情報源検索」が同じ質問理解に基づいて動作することを保証できるため不採用とした。
- **言い換えをLLMではなくルールベース（例:直前の`assistant`発話の主題語を単純に連結する）で行う**: 実装は軽量だが、「XXXという条件です」のような自然文の穴埋め的な発話を単体の質問文へ再構成するには文脈理解が必要であり、ルールベースでは対応しきれない。既存の`summarize.py`・`generate.py`が既にBedrock LLM呼び出しの構成を持っており、同型の呼び出しを追加するコストは小さいため、LLMベースの方式を採用した。

## 結果・影響

- `agent_invitro`に新規モジュール（言い換え質問生成）が追加される。`main/api/server.py`の`_ask_impl`に呼び出し箇所が追加される。
- `select_tags`・`search_knowledge`双方への呼び出しリクエスト数は変わらない（既存の各1回のままで、渡す`query`の値が変わるのみ）。ただし新たにBedrock呼び出しが1回追加されるため、`/ask-pipeline`全体のレイテンシへの影響を実装フェーズで計測する必要がある（REQ-202609091730 12章 Open Issueに準じる形で、実装フェーズの計測事項として記録する）。
- ADR-0086が定める確定タグ（Alias一致）は、`condensed_query`ではなく生のalias一致対象テキストに対して行われる（本ADRの言い換えステップとは独立した入力を使う）。言い換えによって固定エラー文言の文字列がそのまま保持される保証がないため、この分離は必須である（REQ-202609091730 6.2節）。
