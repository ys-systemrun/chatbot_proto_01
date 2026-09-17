import Header from "./Header";
import MessageList from "./messages/MessageList";
import InputBar from "./InputBar";
import { Message } from "../../domain/stateless/message";
import type { AskMode } from "../../domain/stateless/ask_mode";

interface props {
  messages: Message[];
  isLoading: boolean;
  /** 回答生成方式（ADR-0089 決定5）。Header のトグルで切り替える。 */
  askMode: AskMode;
  onChangeAskMode: (mode: AskMode) => void;
  onSubmit: (text: string) => void;
  onEvaluate: (order: number, value: number) => void;
}

export const LayoutContainer: React.FC<props> = ({
  messages,
  isLoading,
  askMode,
  onChangeAskMode,
  onSubmit,
  onEvaluate,
}) => {
  return (
    <div className="app-layout">
      <Header
        askMode={askMode}
        onChangeAskMode={onChangeAskMode}
        disabled={isLoading}
      />
      <MessageList messages={messages} isLoading={isLoading} onEvaluate={onEvaluate} />
      <InputBar onSubmit={onSubmit} disabled={isLoading} />
    </div>
  );
};
