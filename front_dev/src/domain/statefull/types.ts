/** POST /ask のリクエストボディ */
export interface AskRequest {
  session_id: string | null
  text: string
}

/** POST /ask のレスポンスボディ */
export interface AskResponse {
  session_id: string
  answer: string
}

/** チャット画面上の 1 メッセージ */
export type MessageRole = 'user' | 'assistant' | 'error'

export interface MessageItem {
  id: number
  role: MessageRole
  text: string
  rawResponse?: AskResponse
}
