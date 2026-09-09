import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import {
  getTroubleshootingArticle,
  listTagFolders,
  listTags,
  updateTroubleshootingArticle,
} from "../../api";
import type { TroubleshootingUpdateRequest } from "../../domain/admin/troubleshooting";
import type { TagFolder, TagNode } from "../../domain/admin/tag";
import { TagPicker } from "../tag_admin/TagPicker";

const LIST_PATH = "/admin/troubleshooting";

// back パラメータのホワイトリスト検証（オープンリダイレクト対策, ADR-0068）。
function resolveBackTo(back: string | null): string {
  if (back === LIST_PATH || (back && back.startsWith(`${LIST_PATH}?`))) {
    return back;
  }
  return LIST_PATH;
}

// 編集可能なテキストフィールド（title / guidance は必須、その他は任意）。
type FieldKey =
  | "title"
  | "subtitle"
  | "symptom"
  | "operation_history"
  | "error_code"
  | "error_message"
  | "system_environment"
  | "hardware_environment"
  | "version_info"
  | "guidance"
  | "cause"
  | "notes"
  | "keyword_raw";

const TEXTAREA_FIELDS: FieldKey[] = [
  "symptom",
  "error_message",
  "guidance",
  "cause",
  "notes",
  "operation_history",
];

const FIELD_LABELS: Record<FieldKey, string> = {
  title: "タイトル",
  subtitle: "サブ見出し",
  symptom: "現象",
  operation_history: "操作履歴",
  error_code: "エラーコード",
  error_message: "エラーメッセージ",
  system_environment: "システム環境",
  hardware_environment: "ハードウェア環境",
  version_info: "バージョン情報",
  guidance: "ユーザーに案内すべき内容",
  cause: "原因",
  notes: "備考",
  keyword_raw: "キーワード（原文・参考）",
};

const REQUIRED_FIELDS: FieldKey[] = ["title", "guidance"];

const emptyForm = (): Record<FieldKey, string> => ({
  title: "",
  subtitle: "",
  symptom: "",
  operation_history: "",
  error_code: "",
  error_message: "",
  system_environment: "",
  hardware_environment: "",
  version_info: "",
  guidance: "",
  cause: "",
  notes: "",
  keyword_raw: "",
});

export default function TroubleshootingFormPage({
  mode = "edit",
}: {
  mode?: "edit";
}) {
  void mode; // 現状は編集のみ（新規作成は初期スコープ外, ADR-0079）。
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const backTo = resolveBackTo(searchParams.get("back"));

  const [form, setForm] = useState<Record<FieldKey, string>>(emptyForm);
  const [sourceKey, setSourceKey] = useState("");
  const [sourceUpdatedAt, setSourceUpdatedAt] = useState<string | null>(null);
  const [bodyHtml, setBodyHtml] = useState("");
  const [tagIds, setTagIds] = useState<number[]>([]);

  const [tags, setTags] = useState<TagNode[]>([]);
  const [folders, setFolders] = useState<TagFolder[]>([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTags().then(setTags).catch((e) => setError(String(e)));
    listTagFolders().then(setFolders).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!id) return;
    const articleId = Number(id);
    setLoading(true);
    getTroubleshootingArticle(articleId)
      .then((a) => {
        setForm({
          title: a.title ?? "",
          subtitle: a.subtitle ?? "",
          symptom: a.symptom ?? "",
          operation_history: a.operation_history ?? "",
          error_code: a.error_code ?? "",
          error_message: a.error_message ?? "",
          system_environment: a.system_environment ?? "",
          hardware_environment: a.hardware_environment ?? "",
          version_info: a.version_info ?? "",
          guidance: a.guidance ?? "",
          cause: a.cause ?? "",
          notes: a.notes ?? "",
          keyword_raw: a.keyword_raw ?? "",
        });
        setSourceKey(a.source_key);
        setSourceUpdatedAt(a.source_updated_at);
        setBodyHtml(a.body_html);
        setTagIds(a.tags.map((t) => t.id));
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  function setField(key: FieldKey, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!id) return;
    setSaving(true);
    setError(null);
    // 任意フィールドの空文字は null として送る（DB 上 NULL に戻す）。必須は空文字のまま送らない。
    const body: TroubleshootingUpdateRequest = { tag_ids: tagIds };
    (Object.keys(form) as FieldKey[]).forEach((key) => {
      const value = form[key];
      if (REQUIRED_FIELDS.includes(key)) {
        (body as Record<string, unknown>)[key] = value;
      } else {
        (body as Record<string, unknown>)[key] = value.trim() === "" ? null : value;
      }
    });
    try {
      await updateTroubleshootingArticle(Number(id), body);
      navigate(backTo);
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
        <h1 className="admin-title">トラブルシューティング記事編集</h1>
        <Link className="admin-link" to={backTo}>
          ← 一覧へ戻る
        </Link>
      </div>

      {error && <p className="admin-status admin-error">{error}</p>}

      <div className="admin-field">
        <span className="admin-label">出自 / 最終更新日時</span>
        <span className="admin-hint">
          {sourceKey}
          {sourceUpdatedAt ? ` ／ ${sourceUpdatedAt}` : ""}
        </span>
      </div>

      <form className="admin-form" onSubmit={onSubmit}>
        {(Object.keys(FIELD_LABELS) as FieldKey[]).map((key) => (
          <label className="admin-field" key={key}>
            <span className="admin-label">
              {FIELD_LABELS[key]}
              {REQUIRED_FIELDS.includes(key) ? " *" : ""}
            </span>
            {TEXTAREA_FIELDS.includes(key) ? (
              <textarea
                className="admin-textarea"
                value={form[key]}
                onChange={(e) => setField(key, e.target.value)}
                rows={key === "guidance" ? 6 : 3}
                required={REQUIRED_FIELDS.includes(key)}
              />
            ) : (
              <input
                className="admin-input"
                value={form[key]}
                onChange={(e) => setField(key, e.target.value)}
                required={REQUIRED_FIELDS.includes(key)}
              />
            )}
            {key === "guidance" && (
              <span className="admin-hint">
                案内内容・現象・原因・タイトル・サブ見出しを変更すると検索用の埋め込みが再計算されます。
              </span>
            )}
          </label>
        ))}

        <div className="admin-field">
          <span className="admin-label">タグ</span>
          <TagPicker
            tags={tags}
            folders={folders}
            selectedIds={tagIds}
            onChange={setTagIds}
          />
        </div>

        <details className="admin-tagfilter">
          <summary>元HTML（参考・編集不可）</summary>
          <pre className="admin-code">{bodyHtml}</pre>
        </details>

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
