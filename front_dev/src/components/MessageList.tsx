import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import type { MessageItem } from '../domain/statefull/types'

interface MessageListProps {
  messages: MessageItem[]
  isLoading?: boolean
}

export default function MessageList({ messages, isLoading = false }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div id="messages">
      {messages.map(msg => (
        <MessageBubble
          key={msg.id}
          role={msg.role}
          text={msg.text}
          rawResponse={msg.rawResponse}
        />
      ))}
      {isLoading && (
        <div className="message assistant loading">
          <span className="label">アシスタント</span>
          <p className="content">...</p>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
