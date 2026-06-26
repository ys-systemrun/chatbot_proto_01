interface props {
  role: string;
  content: string;
  evaluation?: number | null;
  onEvaluate?: (value: number) => void;
}

export default function MessageBubble({ role, content, evaluation, onEvaluate }: props) {
  const label =
    role === "user" ? "あなた" : role === "error" ? "エラー" : "アシスタント";

  return (
    <div className={`message ${role}`}>
      <span className="label">{label}</span>
      <p className="content">{content}</p>
      {role === "assistant" && onEvaluate && (
        <div className="eval-buttons">
          <button
            className={`eval-btn good${evaluation === 1 ? " active" : ""}`}
            onClick={() => onEvaluate(evaluation === 1 ? 0 : 1)}
            title="良い回答"
          >👍</button>
          <button
            className={`eval-btn bad${evaluation === 2 ? " active" : ""}`}
            onClick={() => onEvaluate(evaluation === 2 ? 0 : 2)}
            title="悪い回答"
          >👎</button>
        </div>
      )}
    </div>
  );
}
