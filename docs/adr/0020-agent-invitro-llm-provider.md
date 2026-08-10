# ADR-0020: `agent_invitro`（実験）が使用するLLM接続先

- ステータス: Accepted
- 日付: 2026-08-06
- 関連: `docs/requirement/202608061621.md`, ADR-0012

## コンテキスト

LangGraphで構築するエージェント（どのMCPツールを呼ぶか、いつ最終回答とするかを判断する側）にはLLMが必要である。既存のTag Selector MCPはADR-0012において、MVP時点のLLM接続先をローカルLLM（LM Studio）としている。`agent_invitro` 側でも同様の論点（ローカルLLM／Amazon Bedrock／OpenAIのいずれを使うか）がある。

発注者より、`agent_invitro` の実験フェーズにおいてもローカルLLM（LM Studio）を使う方針が示された。

## 決定

`agent_invitro` のLangGraphエージェントが使用するLLMは、**実験フェーズではローカルLLM（LM Studio）を使用する**。既存のTag Selector MCP用に用意済みの `LMSTUDIO_CHAT_URL` / `LMSTUDIO_CHAT_MODEL` と同一のチャット補完エンドポイントを再利用する想定とし、`agent_invitro` 専用の別モデルは用意しない（LM Studioで複数のチャット用モデルを同時ロードする運用コストを避ける）。

Amazon Bedrock／OpenAI向けの実装は将来追加できるように、LLM呼び出し部分は抽象化した構成とすることを要件とするが、実験フェーズでは実装を必須としない（ADR-0012と同様の考え方）。

## 検討した代替案

- **MVP時点からAmazon BedrockまたはOpenAIを使用する**: 大規模モデルによりツール呼び出し判断・最終回答生成の精度が期待できる一方、質問文・タグ情報・検索結果を外部APIへ送信することになり、情報の機密区分の確認が別途必要になる（ADR-0012と同様の理由）。実験フェーズの目的（MCPホストとしての結線確認）に対しては、まず社内ネットワーク内で完結するローカルLLMで検証する方がリスクが小さいと判断し、見送った。
- **Tag Selector MCPとは別のローカルLLMモデルを `agent_invitro` 専用にロードする**: エージェントのツール呼び出し判断はTag Selector MCPのタグ判定よりも複雑なタスク（複数ツールからの選択、最終回答生成）であるため、より高性能なモデルを充てる余地はある。ただし実験フェーズではLM Studio側の運用（複数モデル同時ロードによるリソース消費）を複雑にしないため、既存モデルの再利用を優先した。必要になれば追加検討する。

## 結果・影響

- 実験フェーズでは、質問文・タグ情報・検索結果が社外（Bedrock/OpenAI等）へ送信されることはない。
- 一方、現在LM Studioにロードされているチャット用モデル（例: `.env.example` 記載の `google/gemma-4-e4b`）が、LangGraphの一般的なツール呼び出し方式（`bind_tools` 等）が前提とするOpenAI互換のFunction Calling（Tool Calling）に対応しているかは未検証である。対応していない場合、LangGraphのエージェントが期待通りにツールを呼び出せない可能性がある（要件定義書 Open Issue #3）。
- 対応していないことが判明した場合は、プロンプトベースの疑似Function Calling方式への変更、またはTool Calling対応モデルへの切り替え（LM Studio側での追加ロード）を別途検討する。この検証結果次第で、本ADRの内容（使用モデル）を見直す可能性がある。
