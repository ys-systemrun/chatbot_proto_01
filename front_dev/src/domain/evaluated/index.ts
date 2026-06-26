export interface EvaluatedMessage {
  id: string;
  order: number;
  role: number;         // 1=user, 2=assistant
  evaluation: number | null;
  input: string | null;
  model: string | null;
  content: string | null;
  created_at: string;
}

export interface EvaluatedConversation {
  id: string;
  created_at: string;
  messages: EvaluatedMessage[];
}
