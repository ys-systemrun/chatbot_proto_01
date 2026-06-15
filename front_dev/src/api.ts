import type { AskRequest, AskResponse } from './types'

/**
 * POST /ask を呼び出す。
 * Vite のプロキシが http://app:8000/ask へ転送する。
 */
export async function ask(req: AskRequest): Promise<AskResponse> {
  const res = await fetch('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })

  if (!res.ok) {
    const body = await res.text().catch(() => '(no body)')
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`)
  }

  return res.json() as Promise<AskResponse>
}

/**
 * DELETE /session/:sessionId を呼び出す。
 * 存在しない session_id を指定してもエラーにはしない。
 */
export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`/session/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}
