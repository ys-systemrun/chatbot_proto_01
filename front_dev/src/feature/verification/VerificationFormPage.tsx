import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  createVerificationQuestion,
  getVerificationQuestion,
  listTags, // 追加（IMPL-202608261510 T6、既存のタグ管理APIを再利用）
  updateVerificationQuestion,
} from "../../api";
import type { TagNode } from "../../domain/admin/tag"; // 追加

/** タグツリーを平坦なリストへ展開する（既存タグ選択チェックボックス用）。 */
function flattenTags(nodes: TagNode[]): TagNode[] {
  return nodes.flatMap((n) => [n, ...flattenTags(n.children)]);
}

export default function VerificationFormPage({
  mode,
}: {
  mode: "create" | "edit";
}) {
  const { id } = useParams();
  const navigate = useNavigate();

  const [questionText, setQuestionText] = useState("");
  const [memo, setMemo] = useState("");
  const [existingTags, setExistingTags] = useState<string[]>([]); // 追加
  const [allTags, setAllTags] = useState<TagNode[]>([]); // 追加

  const [loading, setLoading] = useState(mode === "edit");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTags()
      .then(setAllTags)
      .catch(() => {}); // 追加: タグ一覧を取得（失敗時は選択肢なしのまま）
  }, []);

  useEffect(() => {
    if (mode === "edit" && id) {
      setLoading(true);
      getVerificationQuestion(Number(id))
        .then((q) => {
          setQuestionText(q.question_text);
          setMemo(q.memo ?? "");
          setExistingTags(q.existing_tags ?? []); // 追加
        })
        .catch((e) => setError(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, id]);

  function toggleExistingTag(name: string) {
    setExistingTags((prev) =>
      prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name],
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (mode === "create") {
        await createVerificationQuestion({
          question_text: questionText,
          memo: memo || null,
          existing_tags: existingTags, // 追加
        });
      } else if (id) {
        await updateVerificationQuestion(Number(id), {
          question_text: questionText,
          memo: memo || null,
          existing_tags: existingTags, // 追加
        });
      }
      navigate("/admin/verification");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="admin-status">読み込み中...</p>;

  const flatTags = flattenTags(allTags);

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">
          {mode === "create" ? "検証質問 新規登録" : "検証質問 編集"}
        </h1>
        <Link className="admin-link" to="/admin/verification">
          ← 一覧へ戻る
        </Link>
      </div>

      {error && <p className="admin-status admin-error">{error}</p>}

      <form className="admin-form" onSubmit={onSubmit}>
        <label className="admin-field">
          <span className="admin-label">質問文</span>
          <textarea
            className="admin-textarea"
            value={questionText}
            onChange={(e) => setQuestionText(e.target.value)}
            rows={3}
            required
          />
        </label>

        <label className="admin-field">
          <span className="admin-label">メモ（任意）</span>
          <input
            className="admin-input"
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
          />
        </label>

        <div className="admin-field">
          <span className="admin-label">既存タグ（任意）</span>
          <p className="admin-hint">
            この質問に対して既に把握しているタグを選択してください。検証実行時、
            select_tags の結果のうちここで選んだタグと同名のものは「新規タグ」として
            記録されません。
          </p>
          <div className="admin-tagpicker">
            {flatTags.map((t) => (
              <label key={t.id} className="admin-tagpicker-item">
                <input
                  type="checkbox"
                  checked={existingTags.includes(t.name)}
                  onChange={() => toggleExistingTag(t.name)}
                />
                {t.name}
              </label>
            ))}
            {flatTags.length === 0 && (
              <span className="admin-muted">登録済みタグがありません</span>
            )}
          </div>
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
