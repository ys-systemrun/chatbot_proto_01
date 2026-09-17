import { ASK_MODES, ASK_MODE_LABEL, type AskMode } from "../../domain/stateless/ask_mode";

interface props {
  // sessionId: string | null
  // onReset: () => void
  /** 現在選択されている回答生成方式（ADR-0089 決定5）。 */
  askMode: AskMode;
  onChangeAskMode: (mode: AskMode) => void;
  /** 応答待ちの間はトグルを操作できないようにする（送信中の方式が混ざるのを防ぐ）。 */
  disabled?: boolean;
}

export default function Header({
  // sessionId,
  // onReset,
  askMode,
  onChangeAskMode,
  disabled = false,
}: props) {
  return (
    <header id="header">
      <h1>Chatbot Debug UI</h1>
      {/* 回答生成方式のトグル。次に送信する質問から選択した方式が使われる（ADR-0089 決定5）。 */}
      <div className="ask-mode-toggle" role="group" aria-label="回答生成方式">
        {ASK_MODES.map((mode) => (
          <button
            key={mode}
            type="button"
            className={`ask-mode-btn${askMode === mode ? " ask-mode-btn-active" : ""}`}
            aria-pressed={askMode === mode}
            disabled={disabled}
            onClick={() => onChangeAskMode(mode)}
          >
            {ASK_MODE_LABEL[mode]}
          </button>
        ))}
      </div>
    </header>
  );
}
