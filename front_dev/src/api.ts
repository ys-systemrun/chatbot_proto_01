import type { AskRequest, AskResponse } from "./domain/statefull/types";
import { Request } from "./domain/stateless/request";
import { Response } from "./domain/stateless/response";
import type { Message } from "./domain/stateless/message";
import type { EvaluatedConversation } from "./domain/evaluated";
import type {
  Category,
  QaDetail,
  QaCreateRequest,
  QaImportResponse,
  QaListParams,
  QaListResponse,
  QaUpdateRequest,
} from "./domain/admin/qa";
import type {
  TagCreateRequest,
  TagImportResponse,
  TagNode,
  TagUpdateRequest,
} from "./domain/admin/tag";
import type {
  QaAlteredCreateRequest,
  QaAlteredImportResponse,
  QaAlteredItem,
  QaAlteredListParams,
  QaAlteredListResponse,
  QaAlteredUpdateRequest,
} from "./domain/admin/question_altered";
import type {
  VerificationEvaluationRequest,
  VerificationImportResponse,
  VerificationQuestionCreateRequest,
  VerificationQuestionDetail,
  VerificationQuestionListResponse,
  VerificationQuestionSummary,
  VerificationQuestionUpdateRequest,
  VerificationRun,
} from "./domain/admin/verification";

/**
 * POST /ask を呼び出す。
 * Vite のプロキシが http://app:8000/ask へ転送する。
 */
export async function ask(req: AskRequest): Promise<AskResponse> {
  const res = await fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "(no body)");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
  }

  return res.json() as Promise<AskResponse>;
}

/**
 * DELETE /session/:sessionId を呼び出す。
 * 存在しない session_id を指定してもエラーにはしない。
 */
export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`/session/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export async function askStateless(req: Request): Promise<Response> {
  const res = await fetch("/api/ask-sl", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "(no body)");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
  }

  return res.json() as Promise<Response>;
}

export async function evaluateResponse(req: {
  conversation_id: string;
  messages: Message[];
}): Promise<void> {
  const res = await fetch("/api/evaluate_response", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "(no body)");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
  }
}

export async function getEvaluatedMessages(): Promise<EvaluatedConversation[]> {
  const res = await fetch("/api/evaluated_messages", {
    headers: { "Accept": "application/json" },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "(no body)");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<EvaluatedConversation[]>;
}

// --------------------------------------------------------------------------- //
// 管理UI用 API（IMPL-202608060837 T16）
// いずれも /api/... へリクエストし、web_backend が Knowledge MCP 経由で処理する。
// エラーレスポンス本文（detail）を含めた Error を送出する（既存パターンを踏襲）。
// --------------------------------------------------------------------------- //
async function jsonFetch<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body?.detail ?? JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => "(no body)");
    }
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/**
 * multipart/form-data で CSV ファイルをアップロードする専用ヘルパー。
 * Content-Type はブラウザに boundary 付きで設定させるため明示しない（jsonFetch とは別実装）。
 */
async function uploadCsv<T>(input: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(input, {
    method: "POST",
    headers: { Accept: "application/json" },
    body: form,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body?.detail ?? JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => "(no body)");
    }
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function listQa(params: QaListParams): Promise<QaListResponse> {
  const q = new URLSearchParams();
  if (params.keyword) q.set("keyword", params.keyword);
  if (params.category) q.set("category", params.category);
  (params.tag_id ?? []).forEach((id) => q.append("tag_id", String(id)));
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  return jsonFetch<QaListResponse>(`/api/qa?${q.toString()}`);
}

export async function getQa(id: string): Promise<QaDetail> {
  return jsonFetch<QaDetail>(`/api/qa/${encodeURIComponent(id)}`);
}

export async function createQa(body: QaCreateRequest): Promise<QaDetail> {
  return jsonFetch<QaDetail>("/api/qa", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateQa(
  id: string,
  body: QaUpdateRequest,
): Promise<QaDetail> {
  return jsonFetch<QaDetail>(`/api/qa/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// QA の削除（ADR-0067）。紐づくタグ・言い換え質問文もカスケード削除される。
export async function deleteQa(id: string): Promise<void> {
  await jsonFetch<void>(`/api/qa/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function listCategories(): Promise<Category[]> {
  const res = await jsonFetch<{ categories: Category[] }>("/api/categories");
  return res.categories;
}

// QA の CSV 一括インポート（IMPL-202608261022 T12）。存在しないタグ名は自動作成される。
export async function importQaCsv(file: File): Promise<QaImportResponse> {
  return uploadCsv<QaImportResponse>("/api/qa/import", file);
}

export async function listTags(parentTagId?: number): Promise<TagNode[]> {
  const q = parentTagId == null ? "" : `?parent_tag_id=${parentTagId}`;
  const res = await jsonFetch<{ tags: TagNode[] }>(`/api/tags${q}`);
  return res.tags;
}

export async function createTag(body: TagCreateRequest): Promise<TagNode> {
  return jsonFetch<TagNode>("/api/tags", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateTag(
  id: number,
  body: TagUpdateRequest,
): Promise<TagNode> {
  return jsonFetch<TagNode>(`/api/tags/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteTag(id: number): Promise<void> {
  await jsonFetch<void>(`/api/tags/${id}`, { method: "DELETE" });
}

// タグの CSV 一括インポート（IMPL-202608261630 T4）。name一致でupsertする。
export async function importTagsCsv(file: File): Promise<TagImportResponse> {
  return uploadCsv<TagImportResponse>("/api/tags/import", file);
}

// タグの CSV エクスポート（IMPL-202608281500 / ADR-0065）。
// 全タグを name/parent_name/description の3列でダウンロードする（そのまま再インポート可能）。
export async function downloadTagsExport(): Promise<void> {
  await downloadBlob("/api/tags/export", "text/csv", "tags.csv");
}

// --------------------------------------------------------------------------- //
// 全データエクスポート（IMPL-202608241600 T22）
// JSON ではなく ZIP（Blob）を扱うため、jsonFetch とは別の専用関数として実装する。
// GET /api/export?format=... のレスポンス Blob を、一時的な <a download> でブラウザの保存
// ダイアログに渡す。ファイル名はサーバの Content-Disposition を優先し、無ければ既定名を使う。
// --------------------------------------------------------------------------- //
export async function downloadExport(format: "sql" | "csv"): Promise<void> {
  await downloadBlob(
    `/api/export?format=${format}`,
    "application/zip",
    `chatbot_invitro_export_${format}.zip`,
  );
}

/**
 * GET のレスポンス Blob を、一時的な <a download> でブラウザの保存ダイアログに渡す共通処理。
 * ファイル名はサーバの Content-Disposition を優先し、無ければ fallbackName を使う。
 */
async function downloadBlob(
  input: string,
  accept: string,
  fallbackName: string,
): Promise<void> {
  const res = await fetch(input, { headers: { Accept: accept } });
  if (!res.ok) {
    const body = await res.text().catch(() => "(no body)");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
  }

  const blob = await res.blob();
  const filename =
    parseFilename(res.headers.get("Content-Disposition")) ?? fallbackName;

  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Content-Disposition ヘッダから filename="..." を取り出す（無ければ null）。 */
function parseFilename(disposition: string | null): string | null {
  if (!disposition) return null;
  const match = /filename="?([^"]+)"?/.exec(disposition);
  return match ? match[1] : null;
}

// --------------------------------------------------------------------------- //
// 検証機能 API（IMPL-202608260909 T12 / IMPL-202608261022 T15）
// --------------------------------------------------------------------------- //
export async function listVerificationQuestions(params: {
  keyword?: string;
  limit?: number;
  offset?: number;
}): Promise<VerificationQuestionListResponse> {
  const q = new URLSearchParams();
  if (params.keyword) q.set("keyword", params.keyword);
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  return jsonFetch<VerificationQuestionListResponse>(
    `/api/verification/questions?${q.toString()}`,
  );
}

export async function createVerificationQuestion(
  body: VerificationQuestionCreateRequest,
): Promise<VerificationQuestionSummary> {
  return jsonFetch<VerificationQuestionSummary>("/api/verification/questions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getVerificationQuestion(
  id: number,
): Promise<VerificationQuestionDetail> {
  return jsonFetch<VerificationQuestionDetail>(
    `/api/verification/questions/${id}`,
  );
}

export async function updateVerificationQuestion(
  id: number,
  body: VerificationQuestionUpdateRequest,
): Promise<VerificationQuestionSummary> {
  return jsonFetch<VerificationQuestionSummary>(
    `/api/verification/questions/${id}`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

export async function deleteVerificationQuestion(id: number): Promise<void> {
  await jsonFetch<void>(`/api/verification/questions/${id}`, {
    method: "DELETE",
  });
}

export async function runVerification(questionId: number): Promise<VerificationRun> {
  return jsonFetch<VerificationRun>(
    `/api/verification/questions/${questionId}/run`,
    { method: "POST" },
  );
}

export async function saveVerificationEvaluation(
  runId: number,
  body: VerificationEvaluationRequest,
): Promise<VerificationRun> {
  return jsonFetch<VerificationRun>(`/api/verification/runs/${runId}/evaluation`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// 検証質問の CSV 一括インポート（IMPL-202608261022 T15）。常に新規追加（重複判定なし）。
export async function importVerificationQuestionsCsv(
  file: File,
): Promise<VerificationImportResponse> {
  return uploadCsv<VerificationImportResponse>(
    "/api/verification/questions/import",
    file,
  );
}

// --------------------------------------------------------------------------- //
// 言い換え質問文（question_altered）管理 API（IMPL-202608281100 / ADR-0064）
// is_primary=false の言い換え行のみを対象とする。/api/question_altered/* を呼び出し、
// web_backend が Knowledge MCP 経由で処理する。
// --------------------------------------------------------------------------- //
export async function listQuestionAltered(
  params: QaAlteredListParams,
): Promise<QaAlteredListResponse> {
  const q = new URLSearchParams();
  if (params.qa_id) q.set("qa_id", params.qa_id);
  if (params.keyword) q.set("keyword", params.keyword);
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  return jsonFetch<QaAlteredListResponse>(`/api/question_altered?${q.toString()}`);
}

export async function getQuestionAltered(id: number): Promise<QaAlteredItem> {
  return jsonFetch<QaAlteredItem>(`/api/question_altered/${id}`);
}

export async function createQuestionAltered(
  body: QaAlteredCreateRequest,
): Promise<QaAlteredItem> {
  return jsonFetch<QaAlteredItem>("/api/question_altered", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateQuestionAltered(
  id: number,
  body: QaAlteredUpdateRequest,
): Promise<QaAlteredItem> {
  return jsonFetch<QaAlteredItem>(`/api/question_altered/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteQuestionAltered(id: number): Promise<void> {
  await jsonFetch<void>(`/api/question_altered/${id}`, { method: "DELETE" });
}

// CSV 一括インポート（id によるupsert。is_primary=true 行を指す行はエラー、他行は継続）。
export async function importQuestionAlteredCsv(
  file: File,
): Promise<QaAlteredImportResponse> {
  return uploadCsv<QaAlteredImportResponse>("/api/question_altered/import", file);
}

// CSV エクスポート（is_primary=false 全件）。そのまま再インポートできる形式でダウンロードする。
export async function downloadQuestionAlteredExport(): Promise<void> {
  await downloadBlob(
    "/api/question_altered/export",
    "text/csv",
    "question_altered_paraphrases.csv",
  );
}
