interface props {
  // sessionId: string | null
  // onReset: () => void
  // disabled?: boolean;
}

export default function Header(
  {
    // sessionId,
    // onReset,
    // disabled = false,
  }: props,
) {
  return (
    <header id="header">
      <h1>Chatbot Debug UI</h1>
    </header>
  );
}
