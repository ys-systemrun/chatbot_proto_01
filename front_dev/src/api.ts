import type { AskRequest, AskResponse } from "./domain/statefull/types";
import { Request } from "./domain/stateless/request";
import { Response } from "./domain/stateless/response";
import type { Message } from "./domain/stateless/message";
import type { EvaluatedConversation } from "./domain/evaluated";
import type {
  Category,
  QaDetail,
  QaCreateRequest,
  QaListParams,
  QaListResponse,
  QaUpdateRequest,
} from "./domain/admin/qa";
import type {
  TagCreateRequest,
  TagNode,
  TagUpdateRequest,
} from "./domain/admin/tag";

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

export async function listCategories(): Promise<Category[]> {
  const res = await jsonFetch<{ categories: Category[] }>("/api/categories");
  return res.categories;
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

// --------------------------------------------------------------------------- //
// 全データエクスポート（IMPL-202608241600 T22）
// JSON ではなく ZIP（Blob）を扱うため、jsonFetch とは別の専用関数として実装する。
// GET /api/export?format=... のレスポンス Blob を、一時的な <a download> でブラウザの保存
// ダイアログに渡す。ファイル名はサーバの Content-Disposition を優先し、無ければ既定名を使う。
// --------------------------------------------------------------------------- //
export async function downloadExport(format: "sql" | "csv"): Promise<void> {
  const res = await fetch(`/api/export?format=${format}`, {
    headers: { Accept: "application/zip" },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "(no body)");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
  }

  const blob = await res.blob();
  const filename =
    parseFilename(res.headers.get("Content-Disposition")) ??
    `chatbot_invitro_export_${format}.zip`;

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
