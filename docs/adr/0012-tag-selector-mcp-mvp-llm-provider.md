# ADR-0012: MVP時点のLLM接続先をローカルLLM（LM Studio）とする

- ステータス: Accepted
- 日付: 2026-08-05
- 関連: `docs/requirement/202608051636.md`, ADR-0009, 要件定義書 Open Issue #4（解消）

## コンテキスト

要件定義書（`docs/requirement/202608051636.md`）4.1節・5.2節では、Tag Selector MCP の `LLMClient` をローカルLLM（LM Studio）／Amazon Bedrock／OpenAIの間で設定により切り替え可能な抽象化として要件定義していたが、MVP時点でどれを主たる接続先とするかは Open Issue #4 として未確定だった。

- 既存の chatbot_invitro（既存appの embedding 呼び出し、Knowledge MCPの想定）は、LM Studio 経由のローカルモデルを利用する構成が既に運用実績としてある。
- Inference Engine（6.4節）で行う処理は、確定済みのタグ候補（Alias辞書で絞り込んだものを含む全件、ADR-0009により現状は数十件程度）から質問文に合致するものを選ばせる比較的軽量な分類タスクであり、大規模モデルでなければ不可能な高度な推論を要求するものではない。
- 発注者より、MVP時点はローカルLLM（LM Studio）を主たる接続先とする方針が示された。

## 決定

Tag Selector MCP の Inference Engine が呼び出すLLMは、**MVP時点ではローカルLLM（LM Studio）を主たる接続先とする**。`LLMClient` インターフェースの実装として `LMStudioLLMClient`（仮称）をMVPで実装し、`LLM_PROVIDER=lmstudio` をデフォルト値とする。Amazon Bedrock／OpenAI向けの実装は `LLMClient` インターフェースを満たす形で将来追加できるように設計するが、MVP時点では実装を必須としない。

## 検討した代替案

- **MVP時点からAmazon BedrockまたはOpenAIを主たる接続先とする**: 大規模モデルによる高い分類精度が期待できる一方、外部APIへ質問文・タグ情報を送信することになり、情報の機密区分の確認（要件定義書 Open Issue #7）が別途必要になる。また、外部API利用に伴うコスト・レイテンシ・可用性（外部サービス障害時の影響）が新たに発生する。MVPの目的（Knowledge MCPと組み合わせた基本機能の確立）に対しては、まず社内ネットワーク内で完結するローカルLLMで精度・応答時間を検証し、必要に応じて外部APIへの切り替えを検討する方が段階的でリスクが小さいと判断し、MVPでの主接続先には採用しなかった。
- **複数プロバイダを同時にサポートし、リクエストごとに切り替える**: 実装・検証コストがMVPの範囲を超えるため見送った。`LLMClient` インターフェースの抽象化により、将来設定変更のみでの切り替えは可能な設計としている。

## 結果・影響

- MVP時点では、質問文・タグ情報が社内ネットワーク外（Bedrock/OpenAI等）へ送信されることがない。これにより、要件定義書8章「セキュリティ」の外部送信に関する機密区分確認は、MVP時点では必須要件ではなくなる（将来Bedrock/OpenAIへ切り替える際に改めて必要になる）。
- Tag Selector MCPの環境変数は、既存 Knowledge MCP・既存appが使用するembedding用のLM Studio接続情報（`LMSTUDIO_EMBEDDING_URL`等）とは別に、チャット補完（タグ判定）用のLM Studioエンドポイント（`LMSTUDIO_CHAT_URL` / `LMSTUDIO_CHAT_MODEL` 等、要件定義書9.3節）を新たに用意する。
- ローカルLLMのモデル性能（分類精度・応答速度）がタグ選択の精度・非機能要件（8章、数秒以内）を満たせるかは、MVP実装・検証フェーズで確認する必要がある。要求水準を満たせない場合、Bedrock/OpenAIへの切り替え、または `max_tags`/`confidence_threshold` の調整、Alias辞書側での確定範囲拡大等の対策を検討する。
- 要件定義書 Open Issue #4 は本ADRの決定により解消済みとする。
