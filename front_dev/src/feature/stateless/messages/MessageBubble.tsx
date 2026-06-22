interface props {
  role: string;
  content: string;
}

export default function MessageBubble({ role, content }: props) {
  const label =
    role === "user" ? "あなた" : role === "error" ? "エラー" : "アシスタント";

  return (
    <div className={`message ${role}`}>
      <span className="label">{label}</span>
      <p className="content">{content}</p>
    </div>
  );
}
