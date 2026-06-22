interface HeaderProps {
  sessionId: string | null
  onReset: () => void
  disabled?: boolean
}

export default function Header({ sessionId, onReset, disabled = false }: HeaderProps) {
  return (
    <header id="header">
      <h1>Chatbot Debug UI</h1>
      <div id="session-bar">
        <span className="session-label">Session ID:</span>
        <code id="session-id-display" title={sessionId ?? ''}>
          {sessionId ?? '（未開始）'}
        </code>
        <button
          id="reset-btn"
          onClick={onReset}
          disabled={disabled}
          title="セッションを削除して会話をリセットする"
        >
          セッションリセット
        </button>
      </div>
    </header>
  )
}
