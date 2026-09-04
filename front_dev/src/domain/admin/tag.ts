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
  // タグフォルダ（分類表示専用メタデータ, ADR-0072）。null は未分類。
  folder_id: number | null;
  // 兄弟集合内の表示順序（ADR-0074）。並べ替えの境界判定は配列位置で行うため
  // 値そのものは通常使わないが、デバッグ・将来のD&D拡張のため保持する。
  display_order: number;
  aliases: TagAlias[];
  children: TagNode[];
}

// タグ・タグフォルダの並べ替え（ADR-0074）。"up"=1つ上へ、"down"=1つ下へ。
export interface TagReorderRequest {
  direction: "up" | "down";
}

export interface TagCreateRequest {
  name: string;
  parent_tag_id?: number | null;
  description?: string | null;
  folder_id?: number | null;
}

// name / description / parent_tag_id / folder_id のいずれか複数を指定できる（送った項目のみ更新）。
// folder_id は送った場合のみ更新（null 指定でタグフォルダを解除）。
export interface TagUpdateRequest {
  name?: string;
  description?: string | null;
  parent_tag_id?: number | null;
  folder_id?: number | null;
}

// タグフォルダマスタ（分類表示専用メタデータ, ADR-0072 で新設、ADR-0073 で階層化）。
// list_tag_folders は parent_folder_id による木構造（children にネスト）で返す。
// name は表示用ラベルで一意性を持たない（同名フォルダが複数存在しうる, ADR-0073）。
export interface TagFolder {
  id: number;
  name: string;
  description: string | null;
  parent_folder_id: number | null;
  // 兄弟集合内の表示順序（ADR-0074）。
  display_order: number;
  children: TagFolder[];
}

export interface TagFolderCreateRequest {
  name: string;
  description?: string | null;
  // 親フォルダ（ADR-0073）。省略/null でルートフォルダとして作成する。
  parent_folder_id?: number | null;
}

export interface TagFolderUpdateRequest {
  name: string;
  description?: string | null;
}

// タグフォルダの移動（ADR-0073）。null でルートフォルダへ移動する。
export interface TagFolderMoveRequest {
  new_parent_folder_id: number | null;
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
