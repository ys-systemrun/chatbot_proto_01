import { useState, useRef } from "react";

interface props {
  onSubmit: (text: string) => void;
  disabled?: boolean;
}

export default function InputBar({ onSubmit, disabled = false }: props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSubmit(text);
    setValue("");
    textareaRef.current?.focus();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      submit();
    }
  };

  return (
    <footer id="input-bar">
      <form id="chat-form" onSubmit={handleSubmit}>
        <textarea
          id="input"
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="質問を入力… (Ctrl+Enter で送信)"
          rows={3}
          disabled={disabled}
          autoFocus
        />
        <button type="submit" id="send-btn" disabled={disabled}>
          {disabled ? "送信中…" : "送信"}
        </button>
      </form>
    </footer>
  );
}
