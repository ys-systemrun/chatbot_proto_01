# ADR-0088: /ask-agentic のAgentic回答生成方式（自前LangGraphループによる検索・十分性評価・クエリ再定式化）

- ステータス: Accepted
- 日付: 2026-09-14
- 関連: `docs/requirement/202609141415_Agentic回答生成エンドポイント新設・APIレイヤ再構成要件定義書.md`, ADR-0022, ADR-0043, ADR-0062, ADR-0084, ADR-0085, ADR-0086, ADR-0089, ADR-0090

## コンテキスト

現行の`agent_invitro`の`POST /ask-pipeline`（`main/api/server.py`の`_ask_impl`）は、「要約畳み込み → `condensed_query`生成（ADR-0085）→ `select_tags` 1回（ADR-0086）→ `search_knowledge` 1回（ADR-0062/0084）→ 回答生成」という一本道の固定パイプラインである。ADR-0043の0章で採られた「単発プロンプト生成方式」であり、LLM呼び出しは3回（要約・言い換え・回答生成）あるが、いずれも**探索の結果を受けて次の行動を決める**呼び出しではない。

このため次の状況に対処できない。（1）`search_knowledge`が0件または無関係な結果を返しても、別の言い方で探し直す機会が一度もない。（2）複合的な質問に対して部分的にしかヒットしなくても、欠落が検知されない。（3）`condensed_query`はLLMによる1回きりの生成であり、外した場合のリカバリがない。しかも`select_tags`と`search_knowledge`の両方が同一の`condensed_query`に依存するため、外れの影響が二重にかかる。`server.py`のソース中にも発注者による`### ↓この辺をもう少しAgenticに？`というコメントが該当区間を囲む形で残されている。

一方、`agent_invitro`にはADR-0022で採用したReActエージェント（`graph/agent.py`の`create_react_agent`）が既に存在する。名目上は「Agentic」だが、ADR-0043の実装ではこの経路は`/ask-pipeline`で使われていない。ReActはツール呼び出しの順序・回数・実行有無をLLMに委ねるため、「ツールを呼ばずに一般知識で答えてしまう」リスクをシステムプロンプトによるベストエフォートのガードでしか抑えられない（`graph/agent.py`のコメント、REQ-202608061621 Open Issue #6）。カスタマーサポート応答という用途では、社内QAに接地しない回答が返ることは許容しがたい。

発注者との協議（2026-09-14）により、Agentic化の方式・探索手段・反復制御・レイテンシ許容度について次の選好が確認された。

- 方式: 自前のLangGraphループ（明示的なノードと条件分岐）を組む。
- 反復判定: LLMによる十分性評価。
- 探索手段: クエリ再定式化による`search_knowledge`再検索、および情報不足時のユーザーへの逆質問。
- レイテンシ許容度: 最大2周回程度。

## 決定

**`POST /ask-agentic`の回答生成を、LangGraphの`StateGraph`で明示的に組んだ探索ループとして実装する。必須ステップ（言い換え・タグ選定・情報源検索・回答生成）は決定論的に固定したまま、「もう一度探すか／何で探すか」という判断のみをLLMに委ねる。ReActエージェント（ADR-0022）へは回帰しない。**

1. **グラフ構造**: `condense` → `select_tags` → （`search` → `assess` の周回）→ `generate` または `clarify`。`condense`・`select_tags`は各1回のみで周回に入らない。周回に入るのは`search`（`search_knowledge` 1回）と`assess`（十分性評価LLM 1回）の組のみである。`create_react_agent`は使わず、`StateGraph`にノードと条件付きエッジを自前で定義する（`graph/agentic_search.py`を新設）。

2. **十分性評価（`assess`）**: 各周回の検索後、Bedrock Converse APIで「ユーザーの質問（`condensed_query`）」「これまでに蓄積された検索結果」「これまでに試したクエリ一覧」を入力に、`{"sufficient": bool, "missing": str, "next_query": str}`のJSON 1件を出力させる。プロンプト定数を自己完結で保持する新規モジュール（`assess.py`）とし、`summarize.py`・`condense.py`と同型の構成を踏襲する。

3. **分岐**: `sufficient=true`なら回答生成へ。`sufficient=false`かつ周回数が上限未満かつ`next_query`が非空なら、`next_query`で再検索して次の周回へ。上限到達時（または`next_query`が空、あるいは既に試したクエリと同一）は、蓄積結果が1件以上あればベストエフォートで回答生成へ、0件なら逆質問へ進む。

4. **探索手段はクエリ再定式化のみ**: 周回ごとに`select_tags`を呼び直すことはしない。タグは初回に選定したものを全周回で共通に使う。`search_knowledge`の`tags`引数はADR-0058/0059により「タグ類似度によるソフトなランキングシグナル」であり、探索の主要な自由度はクエリ側にある。またタグを周回ごとに変えるとBedrock呼び出しと`tag_selector_mcp`呼び出しが同時に増え、レイテンシ許容度（最大2周回）と両立しない。質問の分解（サブクエスチョン化）も、蓄積結果の重複排除・統合の複雑さに見合わないと判断し、本ADRの範囲外とした。

5. **反復上限**: 既定2周回とし、環境変数`AGENTIC_MAX_ITERATIONS`で変更できるようにする。`search_knowledge`の`top_k`も`AGENTIC_SEARCH_TOP_K`（既定3）で設定化する。蓄積件数の上限は`top_k × 上限周回数`（既定6件）とし、結果の`id`（無ければ`title`）で重複排除する。

6. **逆質問（`clarify`）**: 上限まで探索しても蓄積結果が0件の場合、推測で回答せず、Bedrock Converse APIで「回答に必要な具体的な情報を1〜3点に絞って尋ねる」文面を生成して返す（`clarify.py`を新設）。生成に失敗した場合は`generate.py`のシステムプロンプト ルール3と同一の定型文へフォールバックする。

7. **失敗時の縮退**: 十分性評価の呼び出し失敗・JSONパース失敗は`sufficient=true`とみなしてループを抜ける。すなわち、追加要素が全て失敗しても`/ask-agentic`は現行`/ask-pipeline`と同等（1回検索＋回答生成）の挙動へ縮退し、`500`にはならない。`search_knowledge`の失敗はその周回0件としてループを継続する。

8. **回答生成は`/ask-pipeline`と共有**: `generate.py`の`GenerateAnswerLLMBedrock`とそのシステムプロンプトをそのまま使う。回答文の体裁を揃え、A/B比較の際に「検索の当たり方」の差だけを観測できるようにするためである。

9. **ステートレス性の維持**: 周回の状態はリクエスト処理中のグラフ`State`にのみ存在し、レスポンスにも`conversation`データベースにも残さない。会話文脈の持ち回りは`summary`に一本化するというADR-0084の方針を維持する。

## 検討した代替案

- **既存のReActエージェント（ADR-0022, `graph/agent.py`）を`/ask-agentic`に流用する**: 実装コストは最小で、LangGraphの既存資産をそのまま活かせる。しかしツール呼び出しの順序・回数・実行有無がLLM任せであり、「ツールを呼ばずに一般知識で答える」「`select_tags`を飛ばす」「際限なく反復してレイテンシが読めない」といった挙動をプロンプトでしか抑えられない。ADR-0043が`/ask-pipeline`で単発プロンプト方式を選んだ理由（挙動の不安定さ）がそのまま再燃する。カスタマーサポート応答という用途では、社内QAへの接地と応答時間の予測可能性を優先すべきと判断し不採用とした。なお`graph/agent.py`はIPython経由の実験用途としてそのまま残す。

- **LangGraphを使わず、Bedrock Converseのtool-useを`while`ループで自前に回す**: 依存が減り挙動が読みやすい。しかしADR-0021でlangchain-mcp-adapters、ADR-0022でLangGraphを既に採用しており、MCPツールの呼び出しは`langchain-mcp-adapters`のTool経由（`ainvoke`）で統一されている。ここだけBedrockの生tool-useを使うと、MCPツールのスキーマをBedrockのtoolSpecへ変換する処理を自前で持つことになり、ADR-0063で苦労した戻り値パースの問題を別経路でもう一度抱える。既存資産と整合する`StateGraph`方式を採用した。

- **反復判定をスコア閾値等の決定論的ルールで行う（ヒット件数・類似度が閾値未満なら再検索）**: 安価で予測可能。しかし「何が足りないか」を捉えられないため、再検索のクエリを組み立てる手掛かりが得られず、結局同じクエリで探し直すことになりかねない。また`search_knowledge`のスコアはADR-0059で埋め込み類似度とタグ構成類似度を統合したものであり、「回答に十分か」を表す量ではない。発注者確認の結果、LLMによる十分性評価を採用した。ただし十分性評価が失敗した場合の縮退（決定7）により、実質的に「1回で打ち切る」決定論的な下限は担保されている。

- **十分性評価と回答生成を1回のLLM呼び出しに統合する（「回答できるなら回答し、できないなら次のクエリを返す」）**: Bedrock呼び出しを1回減らせる。しかし1回の出力に「回答文」と「制御用の構造化データ」が混在し、パース失敗時の縮退先が「回答が取れない」になるため、失敗時の挙動が悪化する。またログ上で「どの周回で何が不足していたか」を追えなくなる。責務の分離とログの追いやすさを優先して分離した（REQ-202609141415 12章 Open Issue #4に改善案として記録）。

- **周回ごとに`select_tags`を呼び直す／質問をサブクエスチョンへ分解する**: 探索の自由度は上がるが、Bedrockおよび`tag_selector_mcp`の呼び出し回数が周回数に比例して増え、発注者が示したレイテンシ許容度（最大2周回程度）と両立しない。まずクエリ再定式化のみで効果を確認し、必要になれば拡張する段階的な方針を採った。

## 結果・影響

- `agent_invitro`に新規モジュールが追加される: `graph/agentic_search.py`（探索ループの`StateGraph`）、`assess.py`（十分性評価LLM）、`clarify.py`（逆質問生成LLM）、`knowledge.py`（`search_knowledge`呼び出しと結果パース。現行`server.py`の`_extract_results`/`_search_knowledge`の移設）。
- `config.py`に`AGENTIC_MAX_ITERATIONS`（既定2）・`AGENTIC_SEARCH_TOP_K`（既定3）を追加する。既存の`TAG_SELECTOR_MAX_TAGS`等と同様、`load_settings()`の`required`辞書には含めず未設定でも既定値で動作させる。十分性評価・逆質問生成のモデルは`BEDROCK_CHAT_MODEL_ID`を共用し、専用の環境変数は設けない。
- Bedrock呼び出しは`/ask-agentic`で最大6回（要約・言い換え・十分性評価×2・回答生成 or 逆質問生成）、`search_knowledge`呼び出しは最大2回になる。`/ask-pipeline`（最大3回・1回）に対する応答時間の増分は実装フェーズで計測する（REQ-202609141415 12章 Open Issue #1）。
- ADR-0022（ReActエージェント方式）は`graph/agent.py`（IPython実験用途）について有効なまま維持される。`/ask-agentic`はReAct方式を採らないという点で、AWS環境の本番経路における以後の判断は本ADRを優先する。
- ADR-0043の「単発プロンプト生成方式」は`/ask-pipeline`について維持される。両エンドポイントの併存方針はADR-0089による。
- ADR-0085（`condensed_query`）・ADR-0086（Alias確定タグ）は`/ask-agentic`でもそのまま踏襲される（各1回、周回に入らない）。
- 「関連情報が見つからない」ケースの応答が、定型の謝罪文から逆質問へ変わる。会話評価（good/bad）の分布や`conversation`データの傾向が変化しうるため、A/B比較の際は評価データを`/ask-pipeline`期と混ぜて集計しないよう注意する。
