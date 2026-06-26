export interface Message {
  order: number;
  role: string;
  content: string;
  input?: string;           // assistant: LLM に渡したプロンプト
  model?: string;           // assistant: 使用モデル名
  evaluation?: number | null; // user: undefined / assistant: 0=未評価 1=good 2=bad
}
