# ADR-0091: agent_invitro のLLM機能モジュールを `src/llm_tasks/<機能>/` 配下へ再編し、十分性評価に抽象基底クラス（インターフェース）を導入する

- ステータス: Accepted
- 日付: 2026-09-15
- 関連: ADR-0020（LLM接続先）、ADR-0031（AWS環境のBedrock切り替え）、ADR-0032（`src`平坦化）、ADR-0033（設定値の引数注入）、ADR-0085（クエリ言い換え）、ADR-0088（Agentic回答生成）、ADR-0090（APIレイヤ2層分離）、`docs/requirement/202609141415_Agentic回答生成エンドポイント新設・APIレイヤ再構成要件定義書.md`（F-6.3.2 / F-6.3.8 / N-8.6）

## コンテキスト

ADR-0088で新設した十分性評価は、`agent_invitro/src/assess.py` に次の3要素を同居させた形で実装されている。

| 要素 | 内容 |
|---|---|
| プロンプト定義 | `_SYSTEM_PROMPT`、`_build_user_content()`、`_CONTENT_HEAD_CHARS` |
| 出力パース（純関数） | `parse_assessment()`、`_json_candidates()` |
| Bedrock接続の具象実装 | `SufficiencyAssessorBedrock`（boto3 Converse API、失敗時の縮退） |

この構成には、現時点で次の3つの問題がある。

1. **LLMプロバイダの差し替え口が無い。** ADR-0020（ローカルLLM/LM Studio）とADR-0031（AWS環境はBedrock）により、本リポジトリは「環境によってLLM接続先が変わる」ことを前提にしている。実際、`llm.py` は `LLM_PROVIDER` による分岐を持つ。しかし十分性評価だけは `SufficiencyAssessorBedrock` という具象クラス名が `main/api/dependencies.py` に直接importされており（`from ...assess import SufficiencyAssessorBedrock`）、ローカル環境でAgenticループを動かす実装を追加しようとすると、呼び出し側の分岐を都度書き足すことになる。プロバイダ差し替えの境界が、型ではなくクラス名として散在している。

2. **依存の向きが暗黙である。** `graph/agentic_search.py` の `build_agentic_search_graph(search_tool, assessor, ...)` は `assessor` を duck typing で受け取り、要求する契約（`assess(question, results, tried_queries) -> dict` を持つこと、例外を投げないこと、返す dict のキー）はdocstringにしか書かれていない。テスト用スタブ（`tests/test_agentic_assess.py` の `_StubAssessor`）が満たすべき契約も同様にコード上に存在しない。ADR-0090で「ユースケース層はFastAPIに依存しない」という層の境界を引いたが、`assessor` の境界だけは型で表現されていない。

3. **`src/` 直下がモジュールの平置きで飽和しつつある。** ADR-0032の平坦化以降、`src/` 直下には `assess.py`・`clarify.py`・`condense.py`・`generate.py`・`summarize.py`・`tags.py`・`knowledge.py`・`config.py`・`llm.py` が並んでいる。このうち前半6つは「LLMを1回呼んで特定の判断・生成を行う、差し替え可能な機能」という同一の性格を持ち、後半3つ（`knowledge.py`＝MCP呼び出し、`config.py`＝設定、`llm.py`＝LLMクライアント生成）とは性格が異なる。両者が同一階層に平置きされているため、「どれがLLM機能で、どれが基盤か」がファイル名からは読み取れない。

なお `agent_invitro/src/tools/assess/` が空ディレクトリとして先行して作成されているが、`tools` という名称はMCPの「ツール」（`tools/list`・`tools/call`）およびLangGraphのツール呼び出しと字面が衝突するため、本ADRでは採らない（決定1）。

## 決定

**`agent_invitro` の「LLMを呼び出して判断・生成を行う機能モジュール」を `src/llm_tasks/<機能名>/` 配下のサブパッケージへ再編する。その第一弾として `assess.py` を `src/llm_tasks/assess/` へ移設し、同時に十分性評価の抽象基底クラス `SufficiencyAssessor`（`abc.ABC` + `@abstractmethod`）を導入する。**

### 決定1: `src/llm_tasks/` の位置づけと再編方針

`src/llm_tasks/` は、**「LLMまたは外部AIサービスを呼び出し、実装を差し替えうる機能」**を機能単位のサブパッケージとして収める領域とする。対象は次の6機能で、`assess` を先行させ、以降は1機能ずつ段階的に移設する（一度に全機能を動かさない）。

| 機能 | 現行 | 移設先 |
|---|---|---|
| 十分性評価 | `src/assess.py` | `src/llm_tasks/assess/` （本ADRで実施） |
| 逆質問生成 | `src/clarify.py` | `src/llm_tasks/clarify/` （後続） |
| クエリ言い換え | `src/condense.py` | `src/llm_tasks/condense/` （後続） |
| 回答生成 | `src/generate.py` | `src/llm_tasks/generate/` （後続） |
| 会話要約 | `src/summarize.py` | `src/llm_tasks/summarize/` （後続） |
| タグ選定 | `src/tags.py` | `src/llm_tasks/tags/` （後続） |

`knowledge.py`（Knowledge MCPの呼び出しと結果パース）・`config.py`・`llm.py`・`mcp_clients/`・`graph/`・`usecases/`・`main/` は**対象外**とし、現行の位置に据え置く。これらはLLM機能ではなく基盤・配線であり、差し替えの単位が異なる。

ディレクトリ名は `llm_tasks` とする。`tools` は、MCPプロトコルの「ツール」（`tools/list`・`tools/call`、ADR-0002・ADR-0021）およびLangGraphがLLMへ渡す「ツール」（ADR-0022）と字面が衝突し、`src/tools/` がMCPツールの定義・呼び出し側であるかのように読めてしまう。実際のMCPツール呼び出し側は `mcp_clients/`・`knowledge.py` であり、両者を名前の時点で区別する。

**階層は `src/llm_tasks/<機能名>/` の2階層までとし、その下に更にディレクトリを掘らない**（ADR-0032の「階層を増やさない」方針、ADR-0090決定8の「層は2層まで」と同じ抑制を適用する）。

### 決定2: `src/llm_tasks/assess/` のファイル構成

```
agent_invitro/src/llm_tasks/
├── __init__.py
└── assess/
    ├── __init__.py    … 公開API（SufficiencyAssessor / SufficiencyAssessorBedrock / parse_assessment）の再エクスポート
    ├── base.py        … SufficiencyAssessor（抽象基底クラス）と戻り値の定義
    ├── parsing.py     … parse_assessment() / _json_candidates()（純関数。Bedrockに依存しない）
    ├── prompts.py     … _SYSTEM_PROMPT / _build_user_content() / _CONTENT_HEAD_CHARS
    └── bedrock.py     … SufficiencyAssessorBedrock（boto3 Converse API 呼び出しと縮退処理）
```

呼び出し側は原則 `from ..llm_tasks.assess import SufficiencyAssessor` のようにパッケージの公開APIを参照し、`bedrock`・`parsing` 等の下位モジュールを直接importしない（テストが純関数を直接importする場合を除く）。

### 決定3: インターフェースは `abc.ABC` + `@abstractmethod` とする

```python
class SufficiencyAssessor(ABC):
    @abstractmethod
    def assess(
        self, question: str, results: list[dict], tried_queries: list[str]
    ) -> dict: ...
```

契約として次を**docstringではなく仕様として明記**し、実装クラス・テストスタブの双方が従うものとする。

- **同期メソッドである。** boto3をはじめ想定する実装が同期APIであるため、非同期化はしない。呼び出し側（`graph/agentic_search.py`）が `anyio.to_thread` でスレッドプールへ逃がす現行の方式を維持する。
- **例外を送出しない。** LLM呼び出しの失敗・出力のパース失敗はすべて実装内で捕捉し、`{"sufficient": True, "missing": "", "next_query": ""}` を返して探索ループを抜けさせる（F-6.3.8の縮退方針）。失敗は実装側でログに残す（F-6.6.2）。この「投げない」という性質は本インターフェースの中核的な契約であり、ループの制御フローがこれに依存している。
- **戻り値は `{"sufficient": bool, "missing": str, "next_query": str}` の3キーを必ず含む。** `sufficient` が `True` のとき `missing`・`next_query` は空文字列とする。
- **プロンプトの構築と出力のパースは実装の責務**とする。インターフェースは「質問・これまでの検索結果・試行済みクエリを渡すと判定が返る」という粒度に留め、プロンプト形式をインターフェースに含めない（プロバイダごとに最適なプロンプト・出力制約手段が異なるため）。

`typing.Protocol`（既存 `condense.py`・`summarize.py` の `_MessageLike` で使用）ではなく `ABC` を採る理由は代替案の節に記す。

### 決定4: 依存の向きを固定する

- `graph/agentic_search.py`・`usecases/ask_agentic.py` は**抽象（`SufficiencyAssessor`）にのみ依存**し、具象クラス名を持たない。`build_agentic_search_graph` の `assessor` 引数へ型注釈 `SufficiencyAssessor` を付ける。
- **具象の選択は `main/api/dependencies.py` のみが行う**（ADR-0090決定6のDI集約方針を踏襲）。将来ローカルLLM向け実装を追加する場合も、分岐が増えるのはこの1箇所に限定される。
- 具象実装は `Settings` を受け取らず、`model_id`・`region_name`・`max_tokens` 等のプリミティブを引数で受け取る（ADR-0033の方針を維持）。

### 決定5: 互換シムを置かず、参照を一括置換する

`src/assess.py` は削除し、`agent_invitro.assess` という旧importパスは残さない。参照元は `main/api/dependencies.py` と `tests/test_agentic_assess.py`（および `graph/agentic_search.py`・`README.md` 中の記述）に限られ、いずれも本モノレポ内で閉じているため、一括置換で完結する。外部から本パッケージをimportする利用者は存在しない（ADR-0019・ADR-0025の通り、実行形態はコンテナ内の常駐サービスとIPythonシェルに限られる）。

### 決定6: `pyproject.toml` の `packages` へ追記する

ADR-0032で採用した明示列挙方式の帰結として、`agent_invitro.llm_tasks` と `agent_invitro.llm_tasks.assess` を `[tool.setuptools] packages` に追記する。追記漏れは `pip install -e .` 後の `ModuleNotFoundError` として現れる。以降 `src/llm_tasks/` 配下へ機能を移設するたびに同様の追記が必要であり、移設作業の手順に含める。

## 検討した代替案

- **現状維持（`src/assess.py` のまま、duck typing を続ける）**: 変更量ゼロで、Pythonらしい書き方でもある。しかし「例外を投げない」「3キーを返す」という、ループの制御フローが依存している契約がdocstringにしか存在せず、プロバイダ実装を追加した際に契約違反（例外の素通し）が実行時まで検出されない。プロバイダ差し替えが具体的な検討対象になった今、境界を型として固定する価値が変更コストを上回ると判断した。

- **`typing.Protocol`（構造的部分型）を用いる**: 既存の `condense.py`・`summarize.py` が `_MessageLike` で採用済みであり、実装側に継承を強制しないため、既存のテストスタブがそのまま型適合するという利点がある。しかし `_MessageLike` は「外部から渡ってくるオブジェクトの形」を記述するための用途であり、今回のように**自分たちが複数の実装を書き分ける差し替え点**とは目的が異なる。`ABC` であれば実装漏れがインスタンス化時点で `TypeError` として即座に現れ、共通の縮退処理を基底クラスへ引き上げる余地も残る。プロバイダ実装の追加者に対して「この基底を継承せよ」という指示が明示的になる点も採用理由とした（テストスタブは基底を継承する形へ修正する）。

- **`Protocol` + `runtime_checkable`**: 両者の折衷だが、`runtime_checkable` の `isinstance` はメソッド名の有無しか見ず、シグネチャも契約も検証しない。得られる保証が `ABC` より弱い割に構成が複雑になるため不採用とした。

- **ディレクトリ名を `src/tools/` とする**: 既に空ディレクトリが作成されており、短く一般的な名称でもある。しかし本リポジトリでは「ツール」がMCPのツール（`tools/list`・`tools/call`）とLangGraphのツール呼び出しという確立した意味を既に持っており、`src/tools/` がそれらの定義・呼び出し側であるという誤読を招く。実際に置かれるのはMCPツールではなく「LLMに1回問い合わせて判断・生成を得る処理」であるため、意味の衝突しない `llm_tasks` を採用した。

- **プロバイダ軸で配置する（`src/providers/bedrock/assess.py` など）**: 「Bedrock実装を一覧したい」という観点には強い。しかし本プロジェクトで同時に追いたいのは機能単位（十分性評価とは何をするものか）であり、1機能の全体像が複数ディレクトリへ分断される。プロバイダ実装は当面Bedrockのみである一方、機能は6つあるため、機能軸の方が実態に合うと判断した。

- **`llm.py` へ統合し、十分性評価もLLMクライアント生成の一部として扱う**: ファイル数は減るが、`llm.py` はチャットモデルのクライアントを生成する基盤モジュールであり、プロンプトと出力パースを持つ機能モジュールとは責務が異なる。ADR-0033で `llm.py` を設定非依存の薄いモジュールに保った方針とも逆行するため不採用とした。

- **`src/assess.py` を再エクスポートの互換シムとして残す**: 移行を段階的にでき、参照元の修正漏れによる破壊を防げる。しかし参照元が2ファイルしかなく、シムを残すと「正しいimportパスが2つ存在する」状態が定着し、後続の5機能の移設でも同じシムが積み上がる。移行期間を設ける利益が小さいため不採用とした（発注者の選択）。

- **`src/llm_tasks/assess.py`（単一ファイル）として移設する**: 移設だけなら最小の変更で済む。しかしインターフェース・純関数・プロンプト・Bedrock実装を1ファイルに同居させる現状の問題が残り、プロバイダ実装を追加した時点で結局分割が必要になる。最初からサブパッケージ構成とした。

## 結果・影響

- `agent_invitro/src/assess.py`（約180行）が `src/llm_tasks/assess/` 配下の5ファイルへ分割・移設され、`src/assess.py` は削除される。
- `main/api/dependencies.py` の `from ...assess import SufficiencyAssessorBedrock` を新パスへ変更する。DIの組み立て箇所（`"assessor": SufficiencyAssessorBedrock(...)`）の引数は変更しない。
- `graph/agentic_search.py` の `assessor` 引数へ `SufficiencyAssessor` の型注釈を付け、docstringの「`assess.SufficiencyAssessorBedrock` 相当」という記述をインターフェース名に基づく記述へ改める。グラフの挙動は変更しない。
- `tests/test_agentic_assess.py` のimportパスを修正し、`_StubAssessor` を `SufficiencyAssessor` の派生クラスへ改める。テストケースの内容（パース・縮退の検証）は変更しない。これによりインターフェースの契約自体がテストで担保される。
- `agent_invitro/pyproject.toml` の `packages` に `agent_invitro.llm_tasks`・`agent_invitro.llm_tasks.assess` を追加する。**変更後は `pip install -e .` の再実行が必要**であり、再実行しないと `ModuleNotFoundError` が発生する（ADR-0032の「結果・影響」と同種の注意点）。
- `agent_invitro/README.md` のディレクトリ構成図・ファイル役割表を更新する。ADR-0088・ADR-0090に記載されたディレクトリ構成図は当時の決定の記録としてそのまま残し、本ADRが構成を更新した旨を本ADRの関連リンクで辿れるようにする。
- **外部から観測できる挙動は変わらない。** `/ask-agentic` の入出力・ステータスコード・ログの主要項目、およびAgenticループの判定結果は本変更の前後で同一である。`terraform/main/app/main.tf` の `command`（`agent_invitro.main.api.server:app`）・`Dockerfile`・`docker-compose.yml` はいずれも変更不要である（モジュールパスとCOPY対象のディレクトリが変わらないため）。
- ローカルLLM（ADR-0020）向けの十分性評価実装を追加する際は、`src/llm_tasks/assess/` 配下に実装ファイルを1つ追加し、`dependencies.py` に `LLM_PROVIDER` による分岐を1箇所加えるだけで済むようになる。ただし**本ADRではローカルLLM実装の追加は行わない**（インターフェースの新設のみ）。
- 残る5機能（`clarify`・`condense`・`generate`・`summarize`・`tags`）は `src/` 直下に残り、`assess` のみが `src/llm_tasks/` 配下という**過渡的な非対称が一定期間残る**。この非対称は決定1の移設方針をもって許容し、後続の移設は機能単位で個別に実施する（各移設時にインターフェースが必要かどうかは機能ごとに判断し、差し替えの見込みが無い機能に一律で抽象を導入しない）。
- 先行して作成されていた空ディレクトリ `agent_invitro/src/tools/assess/` は使用せず、削除する（Gitは空ディレクトリを追跡しないため、作業環境上のみの削除となる）。
