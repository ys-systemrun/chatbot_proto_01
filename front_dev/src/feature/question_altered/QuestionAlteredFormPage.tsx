import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createQuestionAltered,
  deleteQuestionAltered,
  getQuestionAltered,
  updateQuestionAltered,
} from "../../api";
import { QaPicker } from "../common/QaPicker";

// 言い換え質問文の新規作成・編集フォーム（IMPL-202608281100 / ADR-0064 要件6.2）。
// QaFormPage の mode プロパティによる単一コンポーネント構成を踏襲する。
// 新規: QaPicker で対象QAを選び text を入力。編集: qa_id・タイトルは読み取り専用、text のみ編集。
export default function QuestionAlteredFormPage({
  mode,
}: {
  mode: "create" | "edit";
}) {
  const { id } = useParams();
  const navigate = useNavigate();

  const [qaId, setQaId] = useState("");
  const [qaTitle, setQaTitle] = useState<string | null>(null);
  const [text, setText] = useState("");

  const [loading, setLoading] = useState(mode === "edit");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (mode === "edit" && id) {
      setLoading(true);
      getQuestionAltered(Number(id))
        .then((item) => {
          setQaId(item.qa_id);
          setQaTitle(item.qa_title);
          setText(item.text);
        })
        .catch((e) => setError(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, id]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (mode === "create" && !qaId) {
      setError("対象QAを選択してください。");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (mode === "create") {
        await createQuestionAltered({ qa_id: qaId, text });
      } else if (id) {
        await updateQuestionAltered(Number(id), { text });
      }
      navigate("/admin/question_altered");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function onDelete() {
    if (!id) return;
    if (
      !window.confirm(
        "この言い換え質問文を削除しますか？\n\nこの操作は取り消せません。",
      )
    ) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await deleteQuestionAltered(Number(id));
      navigate("/admin/question_altered");
    } catch (e) {
      setError(String(e));
      setSaving(false);
    }
  }

  if (loading) return <p className="admin-status">読み込み中...</p>;

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">
          {mode === "create" ? "言い換え質問文の新規登録" : "言い換え質問文の編集"}
        </h1>
        <Link className="admin-link" to="/admin/question_altered">
          ← 一覧へ戻る
        </Link>
      </div>

      {error && <p className="admin-status admin-error">{error}</p>}

      <form className="admin-form" onSubmit={onSubmit}>
        <div className="admin-field">
          <span className="admin-label">対象QA</span>
          {mode === "create" ? (
            qaId ? (
              <p className="admin-status">
                選択中: <strong>{qaTitle}</strong>{" "}
                <button
                  className="admin-btn"
                  type="button"
                  onClick={() => {
                    setQaId("");
                    setQaTitle(null);
                  }}
                >
                  変更
                </button>
              </p>
            ) : (
              <QaPicker
                onSelect={(selectedId, title) => {
                  setQaId(selectedId);
                  setQaTitle(title);
                }}
              />
            )
          ) : (
            <p className="admin-status">
              <strong>{qaTitle ?? "（対象QA不明）"}</strong>{" "}
              {qaId && (
                <Link className="admin-link" to={`/admin/qa/${qaId}`}>
                  元の質問文を編集 →
                </Link>
              )}
              <span className="admin-hint"> （対象QAは変更できません）</span>
            </p>
          )}
        </div>

        <label className="admin-field">
          <span className="admin-label">言い換え質問文</span>
          <textarea
            className="admin-textarea"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            required
          />
          <span className="admin-hint">
            保存すると検索用の埋め込みが再計算されます。
          </span>
        </label>

        <div className="admin-form-actions">
          <button
            className="admin-btn admin-btn-primary"
            type="submit"
            disabled={saving}
          >
            {saving ? "保存中..." : "保存"}
          </button>
          {mode === "edit" && (
            <button
              className="admin-btn admin-btn-danger"
              type="button"
              onClick={onDelete}
              disabled={saving}
            >
              削除
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
