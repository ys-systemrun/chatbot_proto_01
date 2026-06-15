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
