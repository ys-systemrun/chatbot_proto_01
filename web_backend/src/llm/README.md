# web_backend/src/llm/ — LLM 呼び出し（回答生成・要約・検索クエリ生成）

チャット応答に使う LLM 呼び出しをまとめたパッケージ。LM Studio（OpenAI 互換 HTTP API）版と Bedrock（boto3 Converse API）版が同一インタフェースで並ぶ（Bedrock 採用は ADR-0031）。web_backend 内では `/api/ask-local`（`chat_controller`）が LM Studio 版を使い、Bedrock 版の呼び出し元は現在 web_backend 内にはない（AWS 上の回答生成は agent_invitro 側が担う）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | 下記の関数・クラスを再エクスポートする。 |
| [`format_query_to_embed.py`](format_query_to_embed.py) | `FormatQueryToEmbed`。直近の質問と会話の要約・履歴から、指示語を具体化したベクトル検索用クエリを LM Studio で生成する。 |
| [`format_query_to_embed_bedrock.py`](format_query_to_embed_bedrock.py) | `FormatQueryToEmbedBedrock`。上記の Bedrock 版（プロンプトは共通、コンストラクタ引数のみ model_id / region_name）。 |
| [`gen_answer_llm.py`](gen_answer_llm.py) | `GenerateAnswerLLM`。カスタマーサポート用システムプロンプトに参考情報・要約・直近履歴・質問を組み込み、LM Studio で回答を生成する。 |
| [`gen_answer_llm_bedrock.py`](gen_answer_llm_bedrock.py) | `GenerateAnswerLLMBedrock`。上記の Bedrock 版（system を別フィールドで渡す）。 |
| [`llm.py`](llm.py) | 初期実装のプロンプト組み立て関数（`get_prompt_00` / `get_prompt_with_role`）と、チャット API を直接叩く `generate_answer` / `generate_answer_stateful`。デバッグスクリプト・CLI チャット・旧 stateful アプリが使用。 |
| [`summarize_llm.py`](summarize_llm.py) | `SummarizeLLM`。会話履歴（必要なら既存要約も踏まえて）を 3 文程度に要約する。失敗時は空文字を返す。 |
| [`summarize_llm_bedrock.py`](summarize_llm_bedrock.py) | `SummarizeLLMBedrock`。上記の Bedrock 版。 |
