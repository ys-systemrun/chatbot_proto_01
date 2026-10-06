export interface Message {
  order: number;
  role: string;
  content: string;
  input?: string;           // assistant: LLM に渡したプロンプト
  model?: string;           // assistant: 使用モデル名
  evaluation?: number | null; // user: undefined / assistant: 0=未評価 1=good 2=bad
  // --- ADR-0099 §1・§4（assistant のみ）---
  release_id?: string | null;         // 回答を生成したリリース
  ask_mode?: string | null;           // "pipeline" | "agentic"
  evaluation_comment?: string | null; // 評価の理由（任意）
}
