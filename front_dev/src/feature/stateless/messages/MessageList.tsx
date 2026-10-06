import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import type { Message } from "../../../domain/stateless/message";

interface props {
  messages: Message[];
  isLoading?: boolean;
  onEvaluate: (order: number, value: number, comment?: string | null) => void;
}

export default function MessageList({ messages, isLoading = false, onEvaluate }: props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div id="messages">
      {messages.map((msg) => (
        <MessageBubble
          key={msg.order}
          role={msg.role}
          content={msg.content}
          evaluation={msg.evaluation}
          evaluationComment={msg.evaluation_comment}
          onEvaluate={msg.role === "assistant"
            ? (value, comment) => onEvaluate(msg.order, value, comment)
            : undefined}
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
  );
}
