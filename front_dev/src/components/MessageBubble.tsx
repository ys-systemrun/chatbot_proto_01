import type { AskResponse } from '../domain/statefull/types'

interface MessageBubbleProps {
  role: 'user' | 'assistant' | 'error'
  text: string
  rawResponse?: AskResponse
}

export default function MessageBubble({ role, text, rawResponse }: MessageBubbleProps) {
  const label = role === 'user' ? 'あなた' : role === 'error' ? 'エラー' : 'アシスタント'

  return (
    <div className={`message ${role}`}>
      <span className="label">{label}</span>
      <p className="content">{text}</p>
      {role === 'assistant' && rawResponse && (
        <details className="raw-response">
          <summary>API レスポンス (JSON)</summary>
          <pre>{JSON.stringify(rawResponse, null, 2)}</pre>
        </details>
      )}
    </div>
  )
}
