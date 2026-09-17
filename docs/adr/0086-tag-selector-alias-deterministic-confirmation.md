# ADR-0086: タグ選定におけるAlias確定タグの決定論的採用と対象範囲

- ステータス: Accepted
- 日付: 2026-09-09
- 関連: `docs/requirement/202609091730_タグ選定・会話文脈管理再設計要件定義書.md`, ADR-0009, ADR-0058, ADR-0059, ADR-0085

## コンテキスト

「アクセス可能なプロテクトキーが見つかりませんというエラーが出ます。」という質問に対し、本来一意に定まるはずの`ContainerNotFound`タグが選定されず、`認証`/`ローカル認証`/`起動エラー`という不正確なタグが選定される不具合が確認された（REQ-202609091730 2.1節）。`conversation.sql`の実データで確認したところ、当該文言は`troubleshooting_article.error_message`に格納された固定のエラー文言であり、本来`tag_alias`による決定論的な一致で処理されるべきケースだった。

`tag_selector_mcp`のコードを確認した結果、`RetrievalEngine.find_tags_by_alias_match()`はAlias一致を検出する仕組みを既に持つが、`InferenceEngine._build_prompt()`はこれを「既に同義語辞書との一致により確定しているタグ」としてLLMへの参考情報として渡すのみであり、最終的な選定・スコアはLLMの推論任せになっていた（ADR-0009はAlias辞書を「候補タグを即時確定・優先付けする」ものと位置付けていたが、実装は「優先付け」に留まり「即時確定」を実現していなかった）。

また、ADR-0085により`select_tags`の`query`は言い換え質問（`condensed_query`）に置き換わることが決定した。LLMによる言い換えは固定エラー文言の文字列をそのまま保持する保証がないため、Alias一致は`condensed_query`ではなく別の生テキストに対して行う必要がある。発注者との協議の結果、このAlias一致対象テキストは「今回の発話＋未要約履歴のうちuser発話」とし、要約済みの履歴は対象外とする（許容する制約）方針で合意した。

## 決定

**`select_tags`の入力に`alias_match_text`（任意、省略時は`query`にフォールバック）を追加する。`RetrievalEngine`は`alias_match_text`に対してAlias一致を行い、検出された確定タグは`InferenceEngine`のLLM推論結果によらず、スコア`1.0`で最終結果へ必ず含める。**

1. **`select_tags`入力スキーマの拡張**（`mcp/schemas.py`の`SELECT_TAGS_INPUT_SCHEMA`）:

   ```
   query: string（必須。LLM推論に使う言い換え質問、ADR-0085）
   alias_match_text: string（任意。省略時はqueryと同じ値を使う）
   max_tags: integer（既定3、変更なし）
   confidence_threshold: number（既定0.0、変更なし。確定タグには適用しない）
   ```

   `alias_match_text`を省略可能かつ`query`へのフォールバックとすることで、`agent_invitro`以外の既存呼び出し元（検証機能、ADR-0049/0060）は変更なしに従来通り動作する。

2. **`RetrievalEngine.retrieve()`の引数拡張**: `retrieve(query: str, alias_match_text: str | None = None)`とし、`find_tags_by_alias_match(alias_match_text or query)`でAlias一致を行う。`candidates`（LLMへ渡す全タグ一覧）は従来通り`query`に依存しない全件取得のままとする。

3. **`InferenceEngine.infer()`の確定タグ強制採用**: LLM応答のパース後、`retrieval_result.confirmed`に含まれる各タグを、スコア`1.0`・`path=[name]`で結果へ追加する（LLMの選定結果に含まれていなくても追加する。重複時はLLM側の値を確定タグの値で上書きする）。`confidence_threshold`によるフィルタは確定タグには適用しない。最終結果は「確定タグ（`id`昇順）＋確定タグに含まれないLLM選定タグ（スコア降順、`confidence_threshold`適用）」を`max_tags`件に切り詰めるが、確定タグ自体は`max_tags`を超えても全件含める。

4. **Alias一致対象テキストの構築（`agent_invitro`側）**: `req.text`＋未要約履歴のうち`role="user"`の`content`を結合し、`alias_match_text`として`select_tags`へ渡す。`role="assistant"`のメッセージ、および要約済み（`summary.summarized_upto`以下の`order`を持つ）履歴は対象外とする（発注者確認済み、REQ-202609091730 6.2〜6.3節）。`user`メッセージの`content`は`web_backend`/`agent_invitro`いずれの実装でも「参考情報:\n{context}\n\n質問:\n{req.text}」という固定テンプレートで構築されているため、`content`から固定文字列`"質問:\n"`以降の部分文字列のみを抽出して結合する（`"質問:\n"`が見つからない場合は`content`全文をフォールバックとして使う）。過去に提示された記事の文言を誤ってAlias一致させないための処理である。

## 検討した代替案

- **確定タグをLLMへのプロンプト内でより強く指示するのみとする（プロンプト工学のみで対応、コード変更なし）**: 実装コストは最小だが、「固定エラー文言なら必ずこのタグになってほしい」という発注者の要求は確実性を求めるものであり、LLMの指示追従性に依存する方式では保証にならない。ADR-0057が「システムプロンプトでの指示（ソフト強制）」を同種の理由で不採用としている前例（「100%保証ではない」）とも整合させ、コード上で確定的に扱う方式を採用した。
- **Alias一致した場合はLLM推論自体をスキップし、確定タグのみを返す**: 実装は単純だが、1つの質問に複数の関連タグ（確定タグ＋LLMが追加で拾うべき周辺タグ）が同時に妥当なケースを想定すると、LLM推論を完全にスキップするのは表現力を落とす。確定タグを「結果への追加保証」として扱い、LLM推論と共存させる方式を採用した。
- **`alias_match_text`を必須パラメータとする（`query`へのフォールバックを設けない）**: `agent_invitro`側の呼び出しは常に`alias_match_text`を渡すため実害はないが、検証機能（ADR-0049/0060）等の既存呼び出し元すべてに変更を強制することになる。後方互換性を優先し、任意パラメータ＋フォールバックとした。
- **`troubleshooting_article.error_message`/`error_code`を`tag_alias`へ自動的に取り込む仕組みを本ADRの範囲に含める**: 今回の不具合の再発防止（他の記事の固定文言も拾えるようにする）には有効だが、Aliasデータの拡充・自動化は「確定タグの扱い方」という本ADRの主眼とは別の問題であり、範囲が広がりすぎる。REQ-202609091730 12章のOpen Issue #3として別途扱うこととし、本ADRの範囲外とした。

## 結果・影響

- `tag_selector_mcp`の`application/retrieval_engine.py`（`retrieve()`引数拡張）、`application/inference_engine.py`（確定タグ強制採用ロジック追加）、`application/select_tags.py`（`alias_match_text`の受け渡し）、`mcp/schemas.py`・`mcp/tools.py`（入力スキーマ拡張）に変更が発生する。`TagMetadataRepository`・`find_tags_by_alias_match`自体のロジック（部分一致判定）は変更しない。
- ADR-0009が定めた「Alias辞書によるルールベース処理＋LLMによる一段階選択」という基本構成は維持されるが、「Alias一致＝即時確定」という当初の意図（ADR-0009コンテキスト、「候補タグを即時確定・優先付けする」）が、実装として初めて実現される。ADR-0009自体を置き換えるものではなく、その未達成だった部分を補完する位置付けとする。
- `select_tags`の呼び出し元のうち、`alias_match_text`を渡さないもの（既存の検証機能等）は、確定タグの仕組みが実質的に無効化される（`find_tags_by_alias_match(query)`が呼ばれ、これは変更前の挙動と同一）。ADR-0085・ADR-0084の`agent_invitro`側の変更が適用されて初めて、本ADRの効果（ContainerNotFoundの確実な選定）が本番の会話フローに反映される。
- `tag_alias`テーブルへの固定エラー文言の登録自体（今回のケースでは「アクセス可能なプロテクトキーが見つかりません」等）は、タグエイリアス管理機能（REQ-202609091119）のUI、または`db_hiroba_qa_init`のシード経由で運用者が別途行う必要がある。本ADRはあくまで「登録されたAliasが確実に効く」ことを保証するものであり、Alias登録そのものは対象外である。
