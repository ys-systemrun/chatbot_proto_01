import type { AskRequest, AskResponse } from "./domain/statefull/types";
import { Request } from "./domain/stateless/request";
import { Response } from "./domain/stateless/response";
import type { Message } from "./domain/stateless/message";
import type { EvaluatedConversation } from "./domain/evaluated";

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
  const res = await fetch("/ask-sl", {
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
  const res = await fetch("/evaluate_response", {
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
  const res = await fetch("/evaluated_messages", {
    headers: { "Accept": "application/json" },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "(no body)");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<EvaluatedConversation[]>;
}
