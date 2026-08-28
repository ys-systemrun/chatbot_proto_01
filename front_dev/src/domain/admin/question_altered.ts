// 言い換え質問文（question_altered）管理の型定義（IMPL-202608281100 / ADR-0064）
// Knowledge MCP / web_backend の QuestionAltered に対応する。is_primary=false の言い換え行のみを扱う。

export interface QaAlteredItem {
  id: number;
  qa_id: string;
  qa_title: string | null;
  text: string;
  is_primary: boolean;
}

export interface QaAlteredListResponse {
  items: QaAlteredItem[];
  total: number;
}

export interface QaAlteredListParams {
  qa_id?: string;
  keyword?: string;
  limit?: number;
  offset?: number;
}

export interface QaAlteredCreateRequest {
  qa_id: string;
  text: string;
}

export interface QaAlteredUpdateRequest {
  text: string;
}

// CSV 一括インポート結果（行単位の部分成功を許容, ADR-0053 と同方針）。
export interface QaAlteredImportRowResult {
  row: number;
  status: "success" | "error";
  id?: number | null;
  error?: string | null;
}

export interface QaAlteredImportResponse {
  total: number;
  success_count: number;
  results: QaAlteredImportRowResult[];
}
