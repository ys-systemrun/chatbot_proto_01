import { useEffect, useState } from "react";

interface props {
  role: string;
  content: string;
  evaluation?: number | null;
  /** 保存済みの評価理由（ADR-0099 §4）。 */
  evaluationComment?: string | null;
  /** 評価値の変更。comment を渡したときは理由も同時に保存する（省略時は既存の理由を保持）。 */
  onEvaluate?: (value: number, comment?: string | null) => void;
}

export default function MessageBubble({
  role,
  content,
  evaluation,
  evaluationComment,
  onEvaluate,
}: props) {
  const label =
    role === "user" ? "あなた" : role === "error" ? "エラー" : "アシスタント";
  const evaluated = evaluation === 1 || evaluation === 2;
  const saved = evaluationComment ?? "";
  const [draft, setDraft] = useState(saved);
  // 👎 を押したら理由欄を開く（👍 は任意。「理由を書く」で開く）。
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setDraft(saved);
  }, [saved]);

  const handleEvaluate = (value: number) => {
    if (!onEvaluate) return;
    if (value === 0) {
      // 評価を取り消すと理由も消す（評価のない理由は意味を持たないため）。
      onEvaluate(0, null);
      setOpen(false);
      return;
    }
    onEvaluate(value);
    setOpen(value === 2 || saved !== "");
  };

  const dirty = draft.trim() !== saved.trim();

  return (
    <div className={`message ${role}`}>
      <span className="label">{label}</span>
      <p className="content">{content}</p>
      {role === "assistant" && onEvaluate && (
        <>
          <div className="eval-buttons">
            <button
              className={`eval-btn good${evaluation === 1 ? " active" : ""}`}
              onClick={() => handleEvaluate(evaluation === 1 ? 0 : 1)}
              title="良い回答"
            >👍</button>
            <button
              className={`eval-btn bad${evaluation === 2 ? " active" : ""}`}
              onClick={() => handleEvaluate(evaluation === 2 ? 0 : 2)}
              title="悪い回答"
            >👎</button>
            {evaluated && !open && (
              <button className="eval-comment-toggle" onClick={() => setOpen(true)}>
                {saved ? "理由を編集" : "理由を書く"}
              </button>
            )}
          </div>
          {evaluated && !open && saved && (
            <p className="eval-comment-saved">理由: {saved}</p>
          )}
          {evaluated && open && (
            <div className="eval-comment">
              <textarea
                className="eval-comment-input"
                value={draft}
                rows={2}
                placeholder={
                  evaluation === 2
                    ? "どこが悪かったか（例: 出典が違う／手順が古い／質問の意図とずれている）"
                    : "良かった点（任意）"
                }
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && dirty) {
                    onEvaluate(evaluation as number, draft.trim() || null);
                    setOpen(false);
                  }
                }}
              />
              <div className="eval-comment-actions">
                <button
                  className="eval-comment-save"
                  disabled={!dirty}
                  onClick={() => {
                    onEvaluate(evaluation as number, draft.trim() || null);
                    setOpen(false);
                  }}
                >
                  理由を保存
                </button>
                <button
                  className="eval-comment-cancel"
                  onClick={() => {
                    setDraft(saved);
                    setOpen(false);
                  }}
                >
                  閉じる
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
