// 検証機能（質問→タグ→情報源）の型定義（IMPL-202608260909 T11 / web_backend の
// verification_controller のレスポンスに対応）。

export interface VerificationTag {
  rank_no: number;
  tag_id: number | null;
  tag_name: string;
  score: number | null;
  path: string[];
}

export interface VerificationSource {
  rank_no: number;
  source_id: string | null;
  source_type: string | null;
  title: string | null;
  content: string | null;
  score: number | null;
  metadata: Record<string, unknown>;
}

export interface VerificationRun {
  id: number;
  executed_at: string;
  status: "success" | "error";
  error_message: string | null;
  max_tags: number | null;
  confidence_threshold: number | null;
  top_k: number | null;
  min_score: number | null;
  tag_selector_latency_ms: number | null;
  knowledge_mcp_latency_ms: number | null;
  evaluation: 0 | 1 | null;
  evaluation_comment: string | null;
  evaluated_at: string | null;
  existing_tags_snapshot: string[]; // IMPL-202608261510 T5
  tags: VerificationTag[];
  sources: VerificationSource[];
}

export interface VerificationQuestionSummary {
  id: number;
  question_text: string;
  memo: string | null;
  existing_tags: string[]; // IMPL-202608261510 T5
  created_at: string;
  latest_run: VerificationRun | null;
}

export interface VerificationQuestionListResponse {
  items: VerificationQuestionSummary[];
  total: number;
}

export interface VerificationQuestionDetail {
  id: number;
  question_text: string;
  memo: string | null;
  existing_tags: string[]; // IMPL-202608261510 T5
  created_at: string;
  updated_at: string;
  runs: VerificationRun[];
}

export interface VerificationQuestionCreateRequest {
  question_text: string;
  memo?: string | null;
  existing_tags?: string[]; // IMPL-202608261510 T5
}

export interface VerificationQuestionUpdateRequest {
  question_text?: string;
  memo?: string | null;
  existing_tags?: string[]; // IMPL-202608261510 T5
}

export interface VerificationEvaluationRequest {
  evaluation: 0 | 1;
  comment?: string | null;
}

// CSV 一括インポート結果（IMPL-202608261022 T15）。
export interface VerificationImportRowResult {
  row: number;
  status: "success" | "error";
  id?: number | null;
  error?: string | null;
}

export interface VerificationImportResponse {
  total: number;
  success_count: number;
  results: VerificationImportRowResult[];
}
