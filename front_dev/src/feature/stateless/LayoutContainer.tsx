import Header from "./Header";
import MessageList from "./messages/MessageList";
import InputBar from "./InputBar";
import { Message } from "../../domain/stateless/message";

interface props {
  messages: Message[];
  isLoading: boolean;
  onSubmit: (text: string) => void;
  onEvaluate: (order: number, value: number) => void;
}

export const LayoutContainer: React.FC<props> = ({
  messages,
  isLoading,
  onSubmit,
  onEvaluate,
}) => {
  return (
    <div className="app-layout">
      <Header />
      <MessageList messages={messages} isLoading={isLoading} onEvaluate={onEvaluate} />
      <InputBar onSubmit={onSubmit} disabled={isLoading} />
    </div>
  );
};
