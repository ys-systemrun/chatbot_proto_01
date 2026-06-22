import { useState, useCallback, useRef } from 'react'
import { ask, deleteSession } from './api'
import type { MessageItem } from './domain/statefull/types'
import Header from './components/Header'
import MessageList from './components/MessageList'
import InputBar from './components/InputBar'

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const nextIdRef = useRef(0)

  const handleSubmit = useCallback(async (text: string) => {
    setMessages(prev => [...prev, { id: ++nextIdRef.current, role: 'user', text }])
    setIsLoading(true)

    try {
      const res = await ask({ session_id: sessionId, text })
      setSessionId(res.session_id)
      setMessages(prev => [
        ...prev,
        { id: ++nextIdRef.current, role: 'assistant', text: res.answer, rawResponse: res },
      ])
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { id: ++nextIdRef.current, role: 'error', text: String(err) },
      ])
    } finally {
      setIsLoading(false)
    }
  }, [sessionId])

  const handleReset = useCallback(async () => {
    if (sessionId) {
      await deleteSession(sessionId).catch(() => {})
    }
    setSessionId(null)
    setMessages([])
  }, [sessionId])

  return (
    <div id="app">
      <Header sessionId={sessionId} onReset={handleReset} disabled={isLoading} />
      <MessageList messages={messages} isLoading={isLoading} />
      <InputBar onSubmit={handleSubmit} disabled={isLoading} />
    </div>
  )
}
