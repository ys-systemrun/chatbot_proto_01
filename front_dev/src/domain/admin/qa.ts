// QA管理の型定義（IMPL-202608060837 T16 / Knowledge MCP の QaSummary/QaDetail に対応）

export interface QaSummary {
  id: string;
  title: string;
  category: string | null;
  tags: string[];
  hiroba_question_altered_count: number;
}

export interface QaTagRef {
  id: number;
  name: string;
}

export interface QaCategoryRef {
  id: number;
  name: string;
}

export interface QaDetail {
  id: string;
  title: string;
  question_text: string;
  answer_text: string;
  category: QaCategoryRef | null;
  tags: QaTagRef[];
  hiroba_question_altered_count: number;
}

export interface QaListResponse {
  items: QaSummary[];
  total: number;
}

export interface QaListParams {
  keyword?: string;
  category?: string;
  tag_id?: number[];
  limit?: number;
  offset?: number;
}

export interface QaCreateRequest {
  title: string;
  question_text: string;
  answer_text: string;
  category_id?: number | null;
  tag_ids?: number[];
}

// 未指定フィールドは「変更なし」。tag_ids は [] で全解除。
export interface QaUpdateRequest {
  title?: string;
  question_text?: string;
  answer_text?: string;
  category_id?: number | null;
  tag_ids?: number[];
}

export interface Category {
  id: number;
  name: string;
}

// CSV 一括インポート結果（IMPL-202608261022 T11/T12）。
export interface QaImportRowResult {
  row: number;
  status: "success" | "error";
  qa_id?: string | null;
  error?: string | null;
}

export interface QaImportResponse {
  total: number;
  success_count: number;
  results: QaImportRowResult[];
}
