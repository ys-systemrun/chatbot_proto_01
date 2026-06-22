import { useCallback, useState } from "react";
import { LayoutContainer } from "./LayoutContainer";
import { Message } from "../../domain/stateless/message";
import { Summary } from "../../domain/stateless/summary";
import { askStateless } from "../../api";

interface props {}

export const StateContainer: React.FC<props> = ({}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [summary, setSummary] = useState<Summary | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);
  const handleSubmit = useCallback(
    async (text: string) => {
      setIsLoading(true);
      const nextOrder =
        messages.length > 0 ? Math.max(...messages.map((m) => m.order)) + 1 : 1;

      setMessages((prev) => [...prev, { order: nextOrder, role: "user", content: text }]);

      try {
        const currentSummary = summary ?? { id: "", content: "", summarized_upto: 0 };
        const res = await askStateless({
          text,
          messages: messages.filter((m) => m.order > currentSummary.summarized_upto),
          summary: currentSummary,
        });

        const displayMessages = res.messages.map((m) =>
          m.order === nextOrder && m.role === "user" ? { ...m, content: text } : m
        );
        setMessages(displayMessages);
        setSummary(res.summary);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            order: (prev.length > 0 ? Math.max(...prev.map((m) => m.order)) : 0) + 1,
            role: "error",
            content: String(err),
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [messages, summary],
  );

  return (
    <LayoutContainer
      messages={messages}
      isLoading={isLoading}
      onSubmit={handleSubmit}
    />
  );
};
