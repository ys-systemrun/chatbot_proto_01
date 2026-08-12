# db_hiroba_qa_initへのembeddingキャッシュ再利用オプション追加 実装指示書

- 文書番号: IMPL-202608121803
- 対象プロジェクト: chatbot_invitro
- 参照文書:
  - ADR `docs/adr/0035-db-hiroba-qa-init-embedding-cache-reuse.md`（ADR-0035、本書が実装指示化する決定）
  - ADR-0018（シード実行制御方式、存在チェックによる冪等性）
  - ADR-0031（AWS環境のLLM/エンベディング接続先をAmazon Bedrockへ切り替え）
  - ADR-0034（シード元データ（CSV/JSON）のイメージ同梱）
  - `docs/implementation_handoff/202608101616_implementation.md`（IMPL-202608101616、`db_hiroba_qa_init/src/embedding.py::get_embedding`のBedrock対応。本書はこのインターフェースを変更しない）
  - `docs/implementation_handoff/202608101542_implementation.md`（IMPL-202608101542、Terraformインフラ構築側）
- 対象コンポーネント: `db_hiroba_qa_init`（アプリケーションコード）、`terraform/envs/verify`（Terraform変数・モジュール呼び出し）。**`knowledge_mcp`・`tag_selector_mcp`・`agent_invitro`は対象外**（ADR-0035はdb_hiroba_qa_initのシード時embedding計算のみを対象とする）。
- 本書の位置づけ: ADR-0035で確定した方針を、実装担当者（開発者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。本書自体はソースコードを含まない（クラス・関数のインターフェース仕様、作業手順、設定値の指示にとどめる）。実際のコード変更は別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確認した現状の実装事実

実装調査の結果、以下を確認した（本書の指示の前提とする）。

| ファイル | 現状の役割 |
|---|---|
| `db_hiroba_qa_init/src/main.py` | エントリポイント。`seed_question_altered()`が、`load_question_altered_csv()`で読み込んだ各行（`embedding=None`）に対し、ループで`get_embedding()`を呼び出してベクトルを計算してから`db.insert_question_altered(rows)`する。テーブルに既にデータがあれば`db.exists_question_altered()`によりこの処理全体をスキップする（ADR-0018）。 |
| `db_hiroba_qa_init/src/embedding.py` | `get_embedding(provider, url, model_name, text, bedrock_region)`。`provider`が`"bedrock"`ならBedrock InvokeModel API、既定（`"lmstudio"`）ならLM Studio互換APIを呼ぶ。本書はこの関数のシグネチャ・実装には変更を加えない。 |
| `db_hiroba_qa_init/src/models.py` | `QuestionAltered`（`qa_id`, `text`, `embedding`, `id`）。`to_tuple()`でINSERT用タプルに変換。 |
| `db_hiroba_qa_init/src/seed_helpers.py` | `load_question_altered_csv(data_dir, question_altered_file)`が`question_altered.csv`（列: `qa_id`, `text`, 任意で`id`）を読み込み、`QuestionAltered`のリストを返す（`embedding`は常に`None`で初期化）。 |
| `db_hiroba_qa_init/Dockerfile` | `COPY data /data`でシード元データ（ADR-0034）をイメージに同梱。 |
| `terraform/envs/verify/main.tf`（`module "db_init_task"`） | `db_init_task`モジュールへ渡す`environment`マップに`EMBEDDING_PROVIDER`/`BEDROCK_EMBEDDING_MODEL_ID`/`EMBEDDING_VECTOR_DIM`等を設定。 |
| `terraform/envs/verify/variables.tf` / `terraform.tfvars.example` | `embedding_vector_dim`・`bedrock_embedding_model_id`等のTerraform変数を定義。 |

## 1. 全体進行フェーズ

| Phase | 目的 | 対象 | 前提 |
|---|---|---|---|
| Phase 1 | キャッシュ読み込みモジュールの実装 | `embedding_cache.py`新設 | なし |
| Phase 2 | シード処理へのキャッシュ利用分岐の組み込み | `main.py::seed_question_altered`更新 | Phase 1 |
| Phase 3 | キャッシュ生成スクリプトの実装 | `export_embedding_cache.py`新設 | Phase 1 |
| Phase 4 | イメージ同梱・ビルドコンテキスト整備 | `Dockerfile`更新、`embedding_cache/`ディレクトリ新設 | Phase 1〜3 |
| Phase 5 | Terraform側のオプション化 | `variables.tf`・`main.tf`・`terraform.tfvars.example`更新 | なし（Phase 1〜4と並行可） |
| Phase 6 | 単体テスト・動作検証 | `test_embedding_cache.py`新設、実機確認 | Phase 1〜5 |

Phase 1〜3はアプリケーションコード側、Phase 5はTerraform側であり、並行して進めてよい。Phase 4はPhase 1〜3完了後に着手する。

## 2. WBS（作業分解構成）

| No. | タスク | Phase | 参照 | 成果物 |
|---|---|---|---|---|
| T1 | `db_hiroba_qa_init/src/embedding_cache.py`新設（`text_hash`, `load_cache`） | 1 | 4.1節 | 新規ファイル |
| T2 | `db_hiroba_qa_init/src/main.py::seed_question_altered`の更新（キャッシュ利用分岐、新規環境変数の読み込み） | 2 | 4.2節 | 差分 |
| T3 | `db_hiroba_qa_init/src/export_embedding_cache.py`新設（キャッシュ生成CLIスクリプト） | 3 | 4.3節 | 新規ファイル |
| T4 | `db_hiroba_qa_init/Dockerfile`の更新（`COPY embedding_cache /embedding_cache`追加） | 4 | 4.4節 | 差分 |
| T5 | `db_hiroba_qa_init/embedding_cache/`ディレクトリ新設（初期は`.gitkeep`のみ、キャッシュ未生成状態でもビルドが通ることを保証） | 4 | 4.4節 | 新規ディレクトリ |
| T6 | `terraform/envs/verify/variables.tf`に`embedding_cache_mode`変数追加 | 5 | 5章 | 差分 |
| T7 | `terraform/envs/verify/main.tf`の`module "db_init_task"`環境変数マップに`EMBEDDING_CACHE_MODE`等を追加 | 5 | 5章 | 差分 |
| T8 | `terraform/envs/verify/terraform.tfvars.example`にコメント・既定値追記 | 5 | 5章 | 差分 |
| T9 | `db_hiroba_qa_init/tests/test_embedding_cache.py`新設（`load_cache`のメタ不一致時フォールバック、`text_hash`一致/不一致時の挙動を単体テスト） | 6 | 9章 | 新規ファイル |
| T10 | 実機確認: キャッシュ未生成環境（既定`off`挙動）→ 通常シード実行 → `export_embedding_cache.py`でキャッシュ生成 → イメージ再ビルド → `EMBEDDING_CACHE_MODE=on`でRDSを空の状態から再シードし、Bedrock呼び出し回数が0件（全件キャッシュhit）になることを確認 | 6 | 9章 | 確認結果 |

## 3. キャッシュ機構の方式整理（ADR-0035 Open Issue 1・2の解消）

ADR-0035で実装フェーズに委ねられていた残課題のうち、キャッシュファイル形式とキャッシュ陳腐化検知の方式を本書で確定する。

- **ファイル形式**: JSON Lines（`.jsonl`、1行1レコードのJSON）を採用する。`question_altered.csv`と同様にCSVで統一する案もあったが、埋め込みベクトル（要素数768〜1024程度の浮動小数点配列）をCSVの1セルに文字列格納すると引用符・区切り文字のエスケープが煩雑になるため、配列をネイティブに表現できるJSONL形式とする。
- **キャッシュの単位**: テーブル単位（ADR-0018の存在チェックの粒度）ではなく、**行単位（`qa_id` + テキストのハッシュ値）**でキャッシュのヒット・ミスを判定する。テーブル単位より細かい粒度にすることで、将来`question_altered.csv`に行が追加された場合でも、キャッシュにない行だけがAPI呼び出しにフォールバックし、既存行はキャッシュを使い続けられる（ADR-0018が対象とする「テーブルへの投入タイミング」の冪等性判定自体は変更しない。あくまでテーブルへの投入が必要になった際の「ベクトルの取得元」を行単位で選べるようにするだけである）。
- **陳腐化検知**: プロバイダ・モデルID・ベクトル次元をメタデータファイルに保持し、シード実行時の環境変数（`EMBEDDING_PROVIDER`・`BEDROCK_EMBEDDING_MODEL_ID`または`MODEL_EMBEDDING`・`EMBEDDING_VECTOR_DIM`）と完全一致しない場合はキャッシュ全体を無効化する（テーブル単位）。テキスト内容の変化は、行単位のハッシュ値不一致として検出する（キャッシュ全体は無効化せず、その行だけAPI呼び出しにフォールバックする）。

## 4. インターフェース仕様（確定版）

### 4.1 `db_hiroba_qa_init/src/embedding_cache.py`（新設、T1）

```python
"""事前計算済みembeddingキャッシュの読み込み（ADR-0035, IMPL-202608121803）。

question_altered のシード時、Bedrock/LM Studioへの埋め込みAPI呼び出しを
必要な場合に限定するためのキャッシュ機構。既定では無効（呼び出し元が
EMBEDDING_CACHE_MODE で明示的に有効化した場合のみ使用される）。
"""

import hashlib
import json
import os


def text_hash(text: str) -> str:
    """テキストのSHA-256ハッシュ（16進文字列）を返す。
    キャッシュ行のテキストと、シード時に読み込んだCSVのテキストが
    一致するかどうかを判定するために使う（完全一致判定のみ、近似は行わない）。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cache(
    cache_dir: str,
    cache_file: str,
    meta_file: str,
    provider: str,
    model_id: str,
    vector_dim: int,
) -> dict[tuple[str, str], list[float]] | None:
    """キャッシュのメタデータが現在の実行環境と一致する場合のみ、
    キャッシュ本体を読み込んで dict を返す。

    Args:
        cache_dir: キャッシュファイルの配置ディレクトリ
                   （既定 "/embedding_cache"、4.4節でイメージに同梱）。
        cache_file: キャッシュ本体のファイル名
                    （既定 "question_altered_embeddings.jsonl"）。
                    各行は {"qa_id": str, "text_hash": str, "embedding": list[float]}
                    形式のJSONオブジェクト。
        meta_file: メタデータファイル名（既定 "question_altered_embeddings.meta.json"）。
                   {"provider": str, "model_id": str, "vector_dim": int,
                    "generated_at": str, "row_count": int} を保持する。
        provider: 現在の実行環境の EMBEDDING_PROVIDER。
        model_id: 現在の実行環境の BEDROCK_EMBEDDING_MODEL_ID または MODEL_EMBEDDING。
        vector_dim: 現在の実行環境の EMBEDDING_VECTOR_DIM（int変換済み）。

    Returns:
        キーを (qa_id, text_hash) のタプル、値を embedding（list[float]）とする dict。
        以下のいずれかに該当する場合は None を返す（キャッシュ不使用、呼び出し元は
        全件を通常のAPI呼び出しにフォールバックすること）。
        - meta_file が存在しない（キャッシュ未生成）。
        - meta_file の provider / model_id / vector_dim が引数と一致しない
          （プロバイダ・モデル切り替え時の安全側フォールバック、ADR-0031関連）。
        - cache_file が存在しない、または読み込み中に例外が発生した場合
          （キャッシュ破損時も処理全体を失敗させず、ログを出力してNoneを返す）。

    呼び出し元（main.py）は、この関数が None を返した場合、または返された dict に
    該当キーが無い場合、既存の get_embedding() 呼び出しにフォールバックする。
    キャッシュの不一致・欠落によって処理が失敗することはない（フェイルセーフ設計）。
    """
    ...
```

### 4.2 `db_hiroba_qa_init/src/main.py::seed_question_altered`の更新（T2）

```python
# 新規環境変数の読み込み（グローバル定義部、既存の EMBEDDING_PROVIDER 等の隣に追加）。
EMBEDDING_CACHE_MODE = os.environ.get("EMBEDDING_CACHE_MODE", "off")  # "on" で有効化
EMBEDDING_CACHE_DIR = os.environ.get("EMBEDDING_CACHE_DIR", "/embedding_cache")
EMBEDDING_CACHE_FILE = os.environ.get(
    "EMBEDDING_CACHE_FILE", "question_altered_embeddings.jsonl"
)
EMBEDDING_CACHE_META_FILE = os.environ.get(
    "EMBEDDING_CACHE_META_FILE", "question_altered_embeddings.meta.json"
)
# 4.3節のキャッシュ生成スクリプトとメタデータ照合の両方で使うため、
# EMBEDDING_VECTOR_DIM をここでも読み込む（既存はマイグレーションのみで使用）。
EMBEDDING_VECTOR_DIM = int(os.environ.get("EMBEDDING_VECTOR_DIM", "0"))


def seed_question_altered():
    print(f"{_now()} ====== Start seeding question_altered...")
    rows = load_question_altered_csv(CSV_DATA_DIR, QUESTION_ALTERED_FILE)
    with DB(DATABASE_URL) as db:
        if db.exists_question_altered():
            print(
                f"{_now()} question_altered table already has data. Skipping insertion."
            )
            return

        cache = None
        if EMBEDDING_CACHE_MODE == "on":
            cache = embedding_cache.load_cache(
                EMBEDDING_CACHE_DIR,
                EMBEDDING_CACHE_FILE,
                EMBEDDING_CACHE_META_FILE,
                EMBEDDING_PROVIDER,
                EMBEDDING_MODEL,
                EMBEDDING_VECTOR_DIM,
            )
            if cache is None:
                print(
                    f"{_now()} EMBEDDING_CACHE_MODE=on but no usable cache found "
                    f"(missing or provider/model/dim mismatch). "
                    f"Falling back to live embedding API calls for all rows."
                )

        cache_hits = 0
        for row in rows:
            if row.embedding is None:
                cached_vec = (
                    cache.get((row.qa_id, embedding_cache.text_hash(row.text)))
                    if cache is not None
                    else None
                )
                if cached_vec is not None:
                    row.embedding = cached_vec
                    cache_hits += 1
                else:
                    row.embedding = get_embedding(
                        EMBEDDING_PROVIDER,
                        EMBEDDING_URL,
                        EMBEDDING_MODEL,
                        row.text,
                        BEDROCK_REGION,
                    )
        if rows:
            print(
                f"{_now()} embedding source: {cache_hits} from cache, "
                f"{len(rows) - cache_hits} via live API call."
            )
            db.insert_question_altered(rows)
    print(f"{_now()} Inserted {len(rows)} question_altered rows.")
```

`import embedding_cache`をファイル先頭のimport群に追加すること。既存のimport構成（`import backfill_title_and_tags`等、パッケージ化せずトップレベルモジュールとして相互import する既存スタイル）に合わせる。

### 4.3 `db_hiroba_qa_init/src/export_embedding_cache.py`（新設、T3）

```python
"""question_altered テーブルから計算済みembeddingをエクスポートし、
キャッシュファイル（4.1節の load_cache が読み込む形式）を生成するCLIスクリプト。

シード処理本体（main.py）とは独立した運用スクリプトであり、db_hiroba_qa_init の
自動実行フロー（main() → migrate() → seed_if_empty()）からは呼び出さない。
運用者が「通常モード（API呼び出し）で1回シードを実行した直後」に、手動で
（またはCI/デプロイスクリプトの明示的なステップとして）実行することを想定する
（ADR-0035 結果・影響の残課題3）。

前提:
- 対象DB（DATABASE_URL）の question_altered テーブルに、EMBEDDING_CACHE_MODE=off
  （通常のAPI呼び出し）でシード済みの全行が存在していること。
- pgvector拡張の embedding 列は psycopg2 が文字列（例 "[0.1,0.2,...]"）として返すため、
  角カッコを除去してカンマ区切りで float に変換するパース処理が必要
  （db_hiroba_qa_init には既存のpgvectorパース処理が無いため、本スクリプト内で実装する。
  knowledge_mcp/web_backend側の類似実装があれば参考にしてよいが、コード共有はしない
  ADR-0016〜0018の既存方針を踏襲する）。

使い方（例、実装時に確定してよい）:
    DATABASE_URL=... EMBEDDING_PROVIDER=bedrock BEDROCK_EMBEDDING_MODEL_ID=... \\
    EMBEDDING_VECTOR_DIM=1024 \\
    python src/export_embedding_cache.py --out-dir /embedding_cache

処理内容:
    1. DATABASE_URL に接続し、
       "SELECT qa_id, text, embedding FROM question_altered ORDER BY id" を実行する。
    2. 各行について、embedding_cache.text_hash(text) でハッシュ化し、
       {"qa_id": qa_id, "text_hash": <hash>, "embedding": [<float>, ...]} を
       question_altered_embeddings.jsonl に1行ずつ書き出す。
    3. {"provider": <EMBEDDING_PROVIDER>, "model_id": <BEDROCK_EMBEDDING_MODEL_ID
       または MODEL_EMBEDDING>, "vector_dim": <EMBEDDING_VECTOR_DIM>,
       "generated_at": <ISO8601文字列>, "row_count": <件数>} を
       question_altered_embeddings.meta.json に書き出す。
    4. 生成した2ファイルの件数・出力先パスを標準出力に表示して終了する
       （終了コード0。DBに1件も無い場合はエラーとして非0終了する）。
"""
...
```

## 4.4 `Dockerfile`・ビルドコンテキストの更新（T4・T5）

```dockerfile
# 既存の COPY data /data の直後に追加。
# 事前計算済みembeddingキャッシュ（任意, ADR-0035）。未生成時は空ディレクトリのまま
# ビルドされ、load_cache() が meta ファイル無しとして自動的にキャッシュ無効モードで動作する。
COPY embedding_cache /embedding_cache
```

`db_hiroba_qa_init/embedding_cache/`ディレクトリを新設し、初期状態では`.gitkeep`（空ファイル）のみを置く。`export_embedding_cache.py`の出力先をこのディレクトリに向けることで、生成後は同ディレクトリの内容がイメージに焼き込まれる（ADR-0034と同じ「イメージ同梱」の考え方）。ローカルdocker-compose環境で`./embedding_cache:/embedding_cache`のようなボリュームマウントを追加すれば、ADR-0034のCSV/JSONと同様に差し替え運用も可能になるが、本書のスコープではボリュームマウントの追加は必須としない（8章 Open Issueに記載）。

## 5. 環境変数・Terraform変数一覧（新規分）

| 変数名 | 種別 | 対象 | 説明 |
|---|---|---|---|
| `EMBEDDING_CACHE_MODE` | 環境変数 | `db_hiroba_qa_init` | **新規**。既定値`"off"`（現行方式維持）。`"on"`にするとキャッシュ再利用を試みる。 |
| `EMBEDDING_CACHE_DIR` | 環境変数 | `db_hiroba_qa_init` | **新規**。既定値`"/embedding_cache"`（4.4節でイメージに同梱したパス）。 |
| `EMBEDDING_CACHE_FILE` | 環境変数 | `db_hiroba_qa_init` | **新規**。既定値`"question_altered_embeddings.jsonl"`。 |
| `EMBEDDING_CACHE_META_FILE` | 環境変数 | `db_hiroba_qa_init` | **新規**。既定値`"question_altered_embeddings.meta.json"`。 |
| `embedding_cache_mode` | Terraform変数（`envs/verify/variables.tf`） | `module.db_init_task` | **新規**。`type = string`, `default = "off"`。`main.tf`の`module "db_init_task"`の`environment`マップに`EMBEDDING_CACHE_MODE = var.embedding_cache_mode`として渡す。 |

`terraform/envs/verify/variables.tf`への追加例:

```hcl
# --- embeddingキャッシュ再利用オプション（ADR-0035, destroy→再apply時のBedrock再計算回避）---
variable "embedding_cache_mode" {
  type        = string
  default     = "off"
  description = "\"on\" にすると db_hiroba_qa_init が事前計算済みembeddingキャッシュ（イメージ同梱）を優先利用し、Bedrock呼び出しをスキップする（ADR-0035）。キャッシュ未生成・プロバイダ/モデル不一致時は自動的に \"off\" と同じ動作にフォールバックする。"
}
```

`terraform/envs/verify/main.tf`の`module "db_init_task"`ブロックへの追加例:

```hcl
  environment = {
    EMBEDDING_VECTOR_DIM       = tostring(var.embedding_vector_dim)
    EMBEDDING_PROVIDER         = "bedrock"
    BEDROCK_EMBEDDING_MODEL_ID = var.bedrock_embedding_model_id
    BEDROCK_REGION             = var.aws_region
    CSV_DATA_DIR               = var.csv_data_dir
    QA_ORIGINAL_FILE           = var.qa_original_file
    QUESTION_ALTERED_FILE      = var.question_altered_file
    CATEGORY_FILE              = var.category_file
    EMBEDDING_CACHE_MODE       = var.embedding_cache_mode  # 追加分（ADR-0035）
  }
```

`terraform/envs/verify/terraform.tfvars.example`への追加例（コメントのみ、既定`"off"`のため未記載でも動作する）:

```hcl
# --- embeddingキャッシュ再利用オプション（ADR-0035）---
# "on" にすると、db_hiroba_qa_init イメージに同梱済みのキャッシュ（あれば）を使い、
# destroy→再apply時のBedrock再計算を避ける。キャッシュ未生成時は自動的に off 相当で動作する。
# embedding_cache_mode = "on"
```

これにより、`terraform apply`実行時に`-var "embedding_cache_mode=on"`を付ける、または`terraform.tfvars`に`embedding_cache_mode = "on"`を記載するだけで、イメージ再ビルドなしにキャッシュ利用を切り替えられる（キャッシュファイル自体は3章の通りイメージ同梱のため、キャッシュの中身を更新する場合はイメージの再ビルド・再pushが必要）。

## 6. 依存関係の追加

新規の外部パッケージ追加は不要（`hashlib`・`json`は標準ライブラリ）。`export_embedding_cache.py`はDB接続に既存の`psycopg2`をそのまま使う。

## 7. 実装順序と依存関係

1. T1（`embedding_cache.py`）を最初に実装する。T2・T3はいずれもT1に依存する。
2. T2（`main.py`更新）・T3（`export_embedding_cache.py`新設）は、T1完了後は並行して進めてよい。
3. T4・T5（Dockerfile・ディレクトリ新設）はT1〜T3完了後に着手する。
4. T6〜T8（Terraform側）は、T1〜T5と並行して進めてよい（アプリケーションコードとTerraformコードは独立している）。
5. T9（単体テスト）はT1完了後、他タスクと並行して書き進めてよい。
6. T10（実機確認）は全タスク完了後、次の順序で実施する。
   1. `EMBEDDING_CACHE_MODE`未設定（既定`off`）のまま、通常どおり`deploy.bat`を実行し、RDSに`question_altered`が投入されることを確認する（回帰確認）。
   2. `export_embedding_cache.py`をECS Exec等で実行し、`embedding_cache/`にキャッシュ2ファイルが生成されることを確認する。
   3. 生成したキャッシュを含めてイメージを再ビルド・再push する。
   4. `destroy.bat`でRDSを含む環境を破棄し、`embedding_cache_mode = "on"`を設定した状態で`deploy.bat`を再実行し、CloudWatch Logsで「embedding source: 1150 from cache, 0 via live API call」のようなログが出ること、Bedrockの`InvokeModel`呼び出し件数が0（またはキャッシュ未収録行のみ）になることを確認する。

## 8. Open Issues（実装時に確定が必要な事項）

1. **キャッシュファイルのサイズ・イメージサイズへの影響**: 埋め込みモデルの次元数（例1024次元）×約1,150件のfloat配列をJSONLで保持した場合の実サイズを実装時に計測し、許容範囲か確認する（ADR-0035 結果・影響）。
2. **`export_embedding_cache.py`の実行手段の確定**: ローカル開発環境からDATABASE_URLを直接指定して実行する運用か、AWS環境ではECS Exec（`aws ecs execute-command`）でタスク内から実行する運用か、あるいは`deploy.ps1`に専用サブコマンド（例: `deploy.ps1 -ExportEmbeddingCache`）を追加するかは実装フェーズで確定する。
3. **キャッシュ更新の運用トリガー**: `question_altered.csv`の内容変更時、または`bedrock_embedding_model_id`/`embedding_vector_dim`の変更時に、キャッシュの再生成を忘れないための運用ルール（チェックリスト、README追記等）を整備する必要がある。忘れた場合でも4.1節のフェイルセーフ設計により誤ったベクトルが使われることはなく、単にキャッシュがヒットせず通常のAPI呼び出しにフォールバックするだけである点は明記しておく。
4. **ローカル開発環境（docker-compose、LM Studio）への適用要否**: 本書はAWS環境の`destroy`→再`apply`運用（ADR-0035の主眼）を対象とするが、環境変数の分岐自体はローカル環境でも動作する。ローカル側で`docker-compose.yml`に`EMBEDDING_CACHE_MODE`等を追加するかは本書のスコープ外とし、必要になった時点で別途判断する。
5. **`embedding_cache/`ディレクトリのGit管理方針**: キャッシュ本体（`.jsonl`/`.meta.json`）は生成物であり、`data/`配下のCSV/JSON（ADR-0034、リポジトリにコミットされている元データ）とは性質が異なる。リポジトリにコミットするか、`.gitignore`対象としてビルド時にのみ生成・配置するかは実装フェーズで確定する。

## 9. テスト・確認観点

- [ ] `load_cache`: メタファイルが存在しない場合に`None`を返すこと。
- [ ] `load_cache`: メタファイルの`provider`/`model_id`/`vector_dim`のいずれかが引数と不一致の場合に`None`を返すこと（ADR-0031のモデル切り替え時次元不一致リスクへのフォールバック確認）。
- [ ] `load_cache`: 全項目が一致する場合、`(qa_id, text_hash)`をキーとする`dict`を正しく返すこと。
- [ ] `text_hash`: 同一テキストに対して常に同一のハッシュ値を返し、1文字でも異なるテキストには異なるハッシュ値を返すこと。
- [ ] `seed_question_altered`: `EMBEDDING_CACHE_MODE=off`（既定）の場合、キャッシュの有無に関わらず既存動作（全件API呼び出し）から変化しないこと（回帰確認）。
- [ ] `seed_question_altered`: `EMBEDDING_CACHE_MODE=on`かつキャッシュがヒットする行について、`get_embedding`が呼び出されないこと（モック・spyで呼び出し回数を検証する）。
- [ ] `seed_question_altered`: `EMBEDDING_CACHE_MODE=on`だがキャッシュに存在しない行（例: CSVに新規追加された行）については、その行のみ`get_embedding`にフォールバックすること。
- [ ] 実機確認（T10）: キャッシュ生成→イメージ再ビルド→destroy→再apply→キャッシュ利用によるBedrock呼び出し削減、の一連の流れが手順通りに機能すること。

## 10. 実装時の注意点・落とし穴

- **フェイルセーフを崩さないこと**: キャッシュの読み込み・照合に失敗した場合は必ず既存のAPI呼び出しにフォールバックし、シード処理自体を失敗させないこと。キャッシュは「あれば使う最適化」であり、必須の依存にしてはならない。
- **pgvector列のパース**: `export_embedding_cache.py`でSELECTした`embedding`列は、psycopg2の既定では文字列（`"[0.1,0.2,...]"`）として返る可能性が高い。`db_hiroba_qa_init`にはこれをパースする既存コードが無いため、新規に実装する必要がある（4.3節参照）。
- **`EMBEDDING_VECTOR_DIM`の取り扱い**: 現状`main.py`はこの環境変数を読んでいない（マイグレーション側のみ）。本書のキャッシュ照合のために`main.py`側でも読み込む必要があるが、値が未設定の環境（ローカルdocker-compose等で明示的に渡していない場合）でも既存の動作（`EMBEDDING_CACHE_MODE=off`）に影響しないよう、既定値の扱いに注意する（例: 未設定時は`0`とし、`load_cache`呼び出し自体を`EMBEDDING_CACHE_MODE=on`の場合のみに限定する）。
- **キャッシュキーに`id`を含めない**: `question_altered.csv`は`id`列が任意（`seed_helpers.py`参照）であり、行の並び順や欠番によって将来的に値が変わり得る。キャッシュのキーは`qa_id`とテキストハッシュのみとし、`id`には依存しないこと。
- **`.gitkeep`の欠落によるビルド失敗**: `embedding_cache/`ディレクトリが空でもDockerの`COPY embedding_cache /embedding_cache`はディレクトリごとコピーできるため`.gitkeep`は必須ではないが、Gitはディレクトリ自体を追跡できないため、キャッシュ未生成状態でも`git clone`直後にディレクトリが存在することを保証するために`.gitkeep`を置く。

## 11. 実装着手前に確認をお願いしたい事項

- 8章のOpen Issue 2（`export_embedding_cache.py`の実行手段）・Open Issue 5（生成物のGit管理方針）は、実装着手前に運用イメージを固めておくと手戻りが少ない。
- 本書はADR-0035の「オプション追加」という決定を実装レベルに落としたものであり、キャッシュファイルの生成・更新自体は依然として運用者が明示的に行う手動（または半自動）の手順である。完全自動化（例: シード元CSV変更を検知して自動でキャッシュを再生成する仕組み）は本書のスコープ外とし、必要であれば別途要件化する。
