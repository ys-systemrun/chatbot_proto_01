// タグ管理の型定義（IMPL-202608060837 T16 / Knowledge MCP の TagNode に対応）

export interface TagAlias {
  id: number;
  alias: string;
}

export interface TagNode {
  id: number;
  name: string;
  parent_tag_id: number | null;
  description: string | null;
  aliases: TagAlias[];
  children: TagNode[];
}

export interface TagCreateRequest {
  name: string;
  parent_tag_id?: number | null;
  description?: string | null;
}

// name / description / parent_tag_id のいずれか複数を指定できる（送った項目のみ更新）。
export interface TagUpdateRequest {
  name?: string;
  description?: string | null;
  parent_tag_id?: number | null;
}

// タグ一括インポートの結果（IMPL-202608261630 T4 / ADR-0061）
export interface TagImportRowResult {
  row: number;
  status: "success" | "error";
  tag_id?: number;
  error?: string;
}

export interface TagImportResponse {
  total: number;
  success_count: number;
  results: TagImportRowResult[];
}
