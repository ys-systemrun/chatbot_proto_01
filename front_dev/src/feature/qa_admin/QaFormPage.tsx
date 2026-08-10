import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  createQa,
  getQa,
  listCategories,
  listTags,
  updateQa,
} from "../../api";
import type { Category } from "../../domain/admin/qa";
import type { TagNode } from "../../domain/admin/tag";
import { TagPicker } from "../tag_admin/TagPicker";

export default function QaFormPage({ mode }: { mode: "create" | "edit" }) {
  const { id } = useParams();
  const navigate = useNavigate();

  const [title, setTitle] = useState("");
  const [questionText, setQuestionText] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [tagIds, setTagIds] = useState<number[]>([]);

  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<TagNode[]>([]);

  const [loading, setLoading] = useState(mode === "edit");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCategories().then(setCategories).catch((e) => setError(String(e)));
    listTags().then(setTags).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (mode === "edit" && id) {
      setLoading(true);
      getQa(id)
        .then((qa) => {
          setTitle(qa.title);
          setQuestionText(qa.question_text);
          setAnswerText(qa.answer_text);
          setCategoryId(qa.category?.id ?? null);
          setTagIds(qa.tags.map((t) => t.id));
        })
        .catch((e) => setError(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, id]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (mode === "create") {
        await createQa({
          title,
          question_text: questionText,
          answer_text: answerText,
          category_id: categoryId,
          tag_ids: tagIds,
        });
      } else if (id) {
        await updateQa(id, {
          title,
          question_text: questionText,
          answer_text: answerText,
          category_id: categoryId,
          tag_ids: tagIds,
        });
      }
      navigate("/admin/qa");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="admin-status">読み込み中...</p>;

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">
          {mode === "create" ? "QA新規登録" : "QA編集"}
        </h1>
        <Link className="admin-link" to="/admin/qa">
          ← 一覧へ戻る
        </Link>
      </div>

      {error && <p className="admin-status admin-error">{error}</p>}

      <form className="admin-form" onSubmit={onSubmit}>
        <label className="admin-field">
          <span className="admin-label">タイトル</span>
          <input
            className="admin-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </label>

        <label className="admin-field">
          <span className="admin-label">質問文</span>
          <textarea
            className="admin-textarea"
            value={questionText}
            onChange={(e) => setQuestionText(e.target.value)}
            rows={3}
            required
          />
          <span className="admin-hint">
            質問文を変更すると検索用の埋め込みが再計算されます。
          </span>
        </label>

        <label className="admin-field">
          <span className="admin-label">回答文</span>
          <textarea
            className="admin-textarea"
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            rows={6}
            required
          />
        </label>

        <label className="admin-field">
          <span className="admin-label">カテゴリ</span>
          <select
            className="admin-input"
            value={categoryId ?? ""}
            onChange={(e) =>
              setCategoryId(e.target.value ? Number(e.target.value) : null)
            }
          >
            <option value="">（未設定）</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>

        <div className="admin-field">
          <span className="admin-label">タグ</span>
          <TagPicker tags={tags} selectedIds={tagIds} onChange={setTagIds} />
        </div>

        <div className="admin-form-actions">
          <button
            className="admin-btn admin-btn-primary"
            type="submit"
            disabled={saving}
          >
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </form>
    </div>
  );
}
