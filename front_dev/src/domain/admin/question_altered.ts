// 言い換え質問文（question_altered）管理の型定義（IMPL-202608281100 / ADR-0064）
// Knowledge MCP / web_backend の QuestionAltered に対応する。is_primary=false の言い換え行のみを扱う。

export interface QaAlteredItem {
  id: number;
  qa_id: string;
  qa_title: string | null;
  text: string;
  is_primary: boolean;
  // 当該行自身の検索対象フラグ（ADR-0092）。
  is_searchable: boolean;
  // 親QAの検索対象フラグ（読み取り専用）。実効検索可否は両者のAND（ADR-0092 決定3）。
  qa_is_searchable: boolean;
}

export interface QaAlteredListResponse {
  items: QaAlteredItem[];
  total: number;
}

export interface QaAlteredListParams {
  qa_id?: string;
  keyword?: string;
  // 行自身の値で絞り込む（未指定＝すべて, ADR-0093 決定7）。
  is_searchable?: boolean;
  limit?: number;
  offset?: number;
}

export interface QaAlteredCreateRequest {
  qa_id: string;
  text: string;
  is_searchable?: boolean; // 省略時は true（検索対象）
}

// いずれも未指定＝変更なし。text 未指定なら embedding は再計算されない（ADR-0093 決定2）。
export interface QaAlteredUpdateRequest {
  text?: string;
  is_searchable?: boolean;
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
