// トラブルシューティング記事管理の型定義（ADR-0079 / Knowledge MCP の
// TroubleshootingSummary / TroubleshootingDetail に対応）。新規作成・削除は初期スコープ外。

export interface TroubleshootingSummary {
  id: number;
  source_key: string;
  title: string;
  subtitle: string | null;
  tags: string[];
  source_updated_at: string | null;
}

export interface TroubleshootingTagRef {
  id: number;
  name: string;
}

export interface TroubleshootingDetail {
  id: number;
  source_key: string;
  title: string;
  subtitle: string | null;
  symptom: string | null;
  operation_history: string | null;
  error_code: string | null;
  error_message: string | null;
  system_environment: string | null;
  hardware_environment: string | null;
  version_info: string | null;
  guidance: string;
  cause: string | null;
  notes: string | null;
  keyword_raw: string | null;
  body_html: string;
  source_updated_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  tags: TroubleshootingTagRef[];
}

export interface TroubleshootingListResponse {
  items: TroubleshootingSummary[];
  total: number;
}

export interface TroubleshootingListParams {
  keyword?: string;
  source_key?: string;
  tag_id?: number[];
  limit?: number;
  offset?: number;
}

// 未指定フィールドは「変更なし」。tag_ids は [] で全解除、未指定で変更なし。
// source_key / body_html / source_updated_at は編集対象外。
export interface TroubleshootingUpdateRequest {
  title?: string;
  subtitle?: string | null;
  symptom?: string | null;
  operation_history?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  system_environment?: string | null;
  hardware_environment?: string | null;
  version_info?: string | null;
  guidance?: string;
  cause?: string | null;
  notes?: string | null;
  keyword_raw?: string | null;
  tag_ids?: number[];
}

export interface SourceKeyListResponse {
  source_keys: string[];
}
