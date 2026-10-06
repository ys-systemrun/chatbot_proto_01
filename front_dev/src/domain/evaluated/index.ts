export interface EvaluatedMessage {
  id: string;
  order: number;
  role: number;         // 1=user, 2=assistant
  evaluation: number | null;
  input: string | null;
  model: string | null;
  content: string | null;
  created_at: string;
  // --- ADR-0099 §1・§4 ---
  release_id: string | null;
  ask_mode: string | null;
  evaluation_comment: string | null;
  evaluated_at: string | null;
  release: Release | null;  // release テーブル未登録なら null（release_id のみ）
}

/** 回答を生成した構成（ADR-0099 §1）。 */
export interface Release {
  release_id: string;
  git_commit: string | null;
  git_dirty: boolean | null;
  prompt_hash: string | null;
  chat_model_id: string | null;
  embedding_model_id: string | null;
  params: Record<string, unknown> | null;
  first_seen_at: string | null;
}

export interface EvaluatedConversation {
  id: string;
  created_at: string;
  messages: EvaluatedMessage[];
}
