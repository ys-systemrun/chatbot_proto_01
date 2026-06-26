import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import type { Message } from "../../../domain/stateless/message";

interface props {
  messages: Message[];
  isLoading?: boolean;
  onEvaluate: (order: number, value: number) => void;
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
          onEvaluate={msg.role === "assistant"
            ? (value) => onEvaluate(msg.order, value)
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
