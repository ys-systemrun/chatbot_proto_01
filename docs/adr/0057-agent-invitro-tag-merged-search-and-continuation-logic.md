# ADR-0057: `agent_invitro`における会話タグの検索反映方式と継続タグ判定ロジック

- ステータス: Accepted（ADR-0062 により改訂: 3節「AND制約を回避する検索方式」のみ単一呼び出し方式に単純化。1・2・4節は維持）
- 日付: 2026-08-26
- 関連: `docs/requirement/202608261330_会話タグ管理機能要件定義書.md`, ADR-0005, ADR-0009, ADR-0010, ADR-0021, ADR-0022, ADR-0043, ADR-0049, ADR-0056

## コンテキスト

ADR-0056により、会話タグはクライアントエコー方式で管理され、`agent_invitro`の`POST /ask-sl`（`main/api/server.py`）がリクエストごとに`req.tags`（クライアント由来の会話タグ）を受け取れるようになった。ユーザーからは、情報源検索への反映方式について「`search_knowledge`に渡すタグは、`select_tags`で得たタグ群とクライアント由来のタグ群をマージしたものとする」との方針が示された（要件定義書2章 回答2）。これは、システムプロンプトによる誘導のような緩い実現ではなく、確実にマージした集合を検索に使うことを求めるものである。

本ADR起票にあたり実装コードを確認した結果、次の2点が判明した。

1. **`POST /ask-sl`は現状`select_tags`を呼んでいない**。ADR-0022が定めたReActエージェント方式（`graph/agent.py`、LLMが自律的に`select_tags`→`search_knowledge`を呼ぶ）は、`main/ipython/main.py`側の実験でのみ使われており、`main/api/server.py`はADR-0043が実装フェーズの選択肢として残していた「単一プロンプト生成方式」を採用した、`search_knowledge`のみを呼ぶ固定シーケンスになっている。したがって、`select_tags`をどう呼ぶかについて、ADR-0022のReActエージェントとの整合を取る必要はなく、`main/api/server.py`内に明示的な呼び出しを追加すればよい。
2. **`knowledge_mcp`の`search_knowledge`の`tags`引数はAND条件である**（`knowledge_mcp/src/knowledge_mcp/repository/qa_repository.py`: 「指定タグをすべて持つQAのみに絞り込む（完全一致・AND条件）」、ADR-0005のタグ関連テーブル方式に基づく実装）。会話タグはターンを重ねるごとに蓄積されうる設計（ADR-0056）であるため、マージ後のタグ集合をそのまま1回の`tags`引数として渡すと、タグ数が増えるほど「全タグを同時に持つQA」は少なくなり、会話が進むほど検索結果が0件に近づくリスクがある。この制約はユーザーが「マージする」と回答した時点では認識されていなかった技術的制約であり、本ADRの決定に大きく影響する。

要件定義書4.1節のスコープにより、本機能はAWS環境（`agent_invitro`）のみを対象とし、`tag_selector_mcp`・`knowledge_mcp`自体には変更を加えない前提を置いている。

## 決定

**`main/api/server.py`の`_ask_impl`に、次の処理を追加する。`tag_selector_mcp`・`knowledge_mcp`のツール自体は変更しない。**

### 1. `select_tags`の明示呼び出し

毎リクエスト、`req.text`を`query`として`select_tags`を直接呼び出す（LLMの自律判断を介さない、ADR-0049の`TagSelectorMcpClient`と同種の「明示呼び出し」パターン）。`max_tags`・`confidence_threshold`は新規環境変数`TAG_SELECTOR_MAX_TAGS`／`TAG_SELECTOR_CONFIDENCE_THRESHOLD`（既定3／0.0、`tag_selector_mcp`自体の既定値と同じ）で指定する。呼び出しに失敗した場合は空集合として扱い、処理を継続する（回答生成自体は失敗させない）。

### 2. クライアント由来タグとのマージ

`select_tags`の結果（`new_tags`）と、クライアントから送られてきた会話タグ（`req.tags`、ADR-0056）を`id`で突き合わせてマージする。マージの具体的な更新規則（`score`・`missed_turns`の扱い）は、4節の継続タグ判定ロジックと同一である（マージタグ＝継続タグとして単一の計算にする）。

### 3. AND制約を回避する検索方式: タグ別複数回呼び出し＋結果の統合

マージタグ全件を1回の`tags`引数にまとめず、**マージタグ1件につき1回、`search_knowledge(query=req.text, tags=[そのタグのname], top_k=N)`を呼び出す**。これに加えて、タグによる絞り込みを行わない`search_knowledge(query=req.text, tags=None, top_k=N)`を1回呼び出す（フォールバック、環境変数`TAG_SEARCH_FALLBACK_ENABLED`、既定`true`で無効化可）。全呼び出しの結果をQA単位（`metadata.guid`）で重複排除し（同一QAは最高スコアを採用）、スコア降順で既存と同じ`top_k`（既定3）件をコンテキスト生成に使う。

呼び出し回数の上限を抑えるため、マージタグ数には新規環境変数`TAG_CONTEXT_MAX_TAGS`（既定5）で上限を設ける。呼び出し回数は最大で「`TAG_CONTEXT_MAX_TAGS`＋1（フォールバック分）」＝既定値では最大6回となる。

### 4. 継続タグ判定ロジック（`missed_turns`によるしきい値方式）

会話タグ1件ごとに`missed_turns`（連続で`select_tags`に再選択されなかった回数）を管理する。

1. `client_tags`のうち、今回の`new_tags`に同じ`id`が含まれるもの: `missed_turns = 0`、`score`を今回の値で更新する。
2. `client_tags`のうち、`new_tags`に含まれないもの: `missed_turns += 1`（`score`は前回値を維持）。
3. `new_tags`のうち、`client_tags`に含まれない（今回新たに選ばれた）もの: `missed_turns = 0`として追加する。
4. `missed_turns`が環境変数`TAG_CONTEXT_MAX_MISSED_TURNS`（既定2）を超えたタグは破棄する。
5. 件数が`TAG_CONTEXT_MAX_TAGS`（既定5）を超える場合、`missed_turns`が大きい順、次に`score`が低い順に間引く。
6. この最終集合を3節の「マージタグ」（その回の検索に使う集合）および`Response.tags`（次回への継続タグ）の両方として使う。

## 検討した代替案

- **システムプロンプトでLLMに「このタグを使うこと」と指示する（ソフト強制）**: ADR-0022の既存のガードレール（`graph/agent.py`の`SYSTEM_PROMPT`強化）と同じ考え方であり、実装は単純である。しかし、（1）ユーザーが求めた「マージしたものとする」という確実性を満たさない（LLMが指示を無視する可能性が残る、ADR-0022自体が「ベストエフォートであり100%保証ではない」と明記している）、（2）そもそも現状の`POST /ask-sl`はReActエージェント（`graph/agent.py`）を経由しない固定シーケンスであり、この案を採るとADR-0022とは別に新たなプロンプト誘導の仕組みを`server.py`に持ち込むことになり、既存の`graph/agent.py`の仕組みと重複する、という2点から不採用とした。
- **マージタグ全件を1回の`tags`引数にまとめて`search_knowledge`を呼ぶ（最も単純な実装）**: 実装コード量は最小だが、AND条件により会話が進むほど検索結果が0件に近づくリスクが高く、MVPとして実用に耐えないと判断し不採用とした（コンテキスト2節）。
- **`knowledge_mcp`の`search_knowledge`をOR条件（または「N件以上一致」のような部分一致条件）に対応させる**: AND制約の問題を根本的に解決できる、最も筋の良い解決策である。しかし、要件定義書4.1節のスコープ（`tag_selector_mcp`・`knowledge_mcp`は変更しない）に反する。将来、タグ別複数回呼び出し方式（本決定の3節）のレイテンシが問題になった場合の改善候補として、要件定義書12章のOpen Issueに記録する。
- **継続タグ判定を`conversation`データベースの永続カウンタで行う（`missed_turns`をサーバー側DBで管理）**: サーバー側の実装は多少単純になるが、ADR-0056が決定した「DB非永続化・クライアントエコー方式」と矛盾するため不採用とした。`missed_turns`をクライアントが単に往復させるだけの不透明な値として扱うことで、サーバー側の状態を持たずに同等のロジックを実現できる。
- **`select_tags`の呼び出しをクライアント由来タグごとに個別実行し、スコアを再計算する（タグごとの関連度を都度算出）**: `select_tags`は「質問文→タグ集合」を返すツールであり、「質問文とあるタグの関連度」を単体で返すインターフェースを持たない（ADR-0010）。個別スコアの再計算には`tag_selector_mcp`側の変更が必要になり、スコープ外であるため不採用とした。今回の質問文に対する`select_tags`の結果に含まれるかどうか（`id`一致）のみで再選択の有無を判定する簡易な方式（本決定の4節）を採用した。

## 結果・影響

- `agent_invitro/src/main/api/server.py`の`_ask_impl`に、`select_tags`呼び出し・マージ・複数回`search_knowledge`呼び出し・重複排除・継続タグ判定の各ロジックが追加される。ロジック量が増えるため、実装フェーズで新規モジュール（例: `agent_invitro/src/tags.py`）への切り出しを検討する。
- `agent_invitro/src/mcp_clients/client.py`自体への変更は不要（既存の`load_tools`が返すツール一覧から`select_tags`ツールを取得するだけでよい）。
- `terraform/main/app/main.tf`の`module "agent_invitro"`の`environment`に、`TAG_SELECTOR_MAX_TAGS`・`TAG_SELECTOR_CONFIDENCE_THRESHOLD`・`TAG_CONTEXT_MAX_TAGS`・`TAG_CONTEXT_MAX_MISSED_TURNS`・`TAG_SEARCH_FALLBACK_ENABLED`の5変数が追加される。ネットワーク（`terraform/modules/network`）の変更は不要（`agent_invitro → tag_selector_mcp`の到達性は既存）。
- 1リクエストあたりの`search_knowledge`呼び出し回数が最大6回（既定値）に増え、`select_tags`呼び出しが新たに毎回発生する。`/ask-sl`全体のレイテンシへの影響を実装フェーズで計測する必要がある（要件定義書12章 Open Issue #5）。
- `tag_selector_mcp`への呼び出し元が、既存の`agent_invitro`（`graph/agent.py`のReActエージェント、実験用）・`web_backend`（ADR-0049の検証機能）に加えて、`agent_invitro`の`POST /ask-sl`からも発生するようになる。運用開始後、`tag_selector_mcp`への負荷を監視する必要がある。
- `graph/agent.py`（ADR-0022）・`tag_selector_mcp`・`knowledge_mcp`のコード・ツール仕様には変更を加えない。
