import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import {
  deleteQa,
  importQaCsv,
  listCategories,
  listQa,
  listTagFolders,
  listTags,
} from "../../api";
import type {
  Category,
  QaImportResponse,
  QaSummary,
} from "../../domain/admin/qa";
import type { TagFolder, TagNode } from "../../domain/admin/tag";
import { TagPicker } from "../tag_admin/TagPicker";
import { QA_DELETE_CONFIRM } from "./deleteConfirm";

const PAGE_SIZE = 20;

// URL の page（1始まり）を内部 offset（0始まり）へ変換する。不正値・未指定は先頭ページ扱い。
function pageParamToOffset(pageParam: string | null): number {
  const page = Number(pageParam);
  if (!Number.isInteger(page) || page < 1) return 0;
  return (page - 1) * PAGE_SIZE;
}

export default function QaListPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const [items, setItems] = useState<QaSummary[]>([]);
  const [total, setTotal] = useState(0);
  // マウント時に URL クエリから初期検索条件・ページ位置を復元する（ADR-0068）。
  const [offset, setOffset] = useState(() =>
    pageParamToOffset(searchParams.get("page")),
  );

  const [keyword, setKeyword] = useState(() => searchParams.get("keyword") ?? "");
  const [category, setCategory] = useState(
    () => searchParams.get("category") ?? "",
  );
  const [tagIds, setTagIds] = useState<number[]>(() =>
    searchParams
      .getAll("tag_id")
      .map((v) => Number(v))
      .filter((n) => Number.isInteger(n) && n > 0),
  );

  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<TagNode[]>([]);
  const [folders, setFolders] = useState<TagFolder[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 削除中の QA id（当該行の削除ボタンを無効化する, ADR-0067）
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // CSV インポート状態（IMPL-202608261022 T12）
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<QaImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // フィルタ用のカテゴリ・タグを初回に取得する
  useEffect(() => {
    listCategories().then(setCategories).catch((e) => setError(String(e)));
    listTags().then(setTags).catch((e) => setError(String(e)));
    listTagFolders().then(setFolders).catch((e) => setError(String(e)));
  }, []);

  // 現在の検索条件と nextOffset から URL クエリを構築し、履歴を replace で同期する。
  // 既定値（空文字列・空配列・page=1）に該当するパラメータは URL から省略する（ADR-0068）。
  function syncUrl(nextOffset: number) {
    const next = new URLSearchParams();
    if (keyword) next.set("keyword", keyword);
    if (category) next.set("category", category);
    tagIds.forEach((id) => next.append("tag_id", String(id)));
    const page = Math.floor(nextOffset / PAGE_SIZE) + 1;
    if (page > 1) next.set("page", String(page));
    setSearchParams(next, { replace: true });
  }

  function load(nextOffset: number) {
    setLoading(true);
    setError(null);
    listQa({
      keyword: keyword || undefined,
      category: category || undefined,
      tag_id: tagIds.length ? tagIds : undefined,
      limit: PAGE_SIZE,
      offset: nextOffset,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
        setOffset(nextOffset);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
    syncUrl(nextOffset);
  }

  useEffect(() => {
    load(offset);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    load(0);
  }

  async function onDelete(id: string) {
    if (!window.confirm(QA_DELETE_CONFIRM)) return;
    setDeletingId(id);
    setError(null);
    try {
      await deleteQa(id);
      // 削除後は現在ページを再読込する。ページ内の最後の1件を消した場合は前ページへ送る。
      const nextOffset =
        items.length === 1 && offset > 0 ? offset - PAGE_SIZE : offset;
      load(nextOffset);
    } catch (e) {
      setError(String(e));
    } finally {
      setDeletingId(null);
    }
  }

  async function onImport() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setImportError("CSV ファイルを選択してください。");
      return;
    }
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const result = await importQaCsv(file);
      setImportResult(result);
      if (fileRef.current) fileRef.current.value = "";
      load(0);
    } catch (e) {
      setImportError(String(e));
    } finally {
      setImporting(false);
    }
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // 編集・新規作成ページへ現在の一覧 URL（検索条件・ページ位置）を back として引き継ぐ（ADR-0068）。
  const backParam = encodeURIComponent(location.pathname + location.search);

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">QA一覧</h1>
        <Link
          className="admin-btn admin-btn-primary"
          to={`/admin/qa/new?back=${backParam}`}
        >
          ＋ 新規QA
        </Link>
      </div>

      <form className="admin-filters" onSubmit={onSearch}>
        <input
          className="admin-input"
          placeholder="キーワード（タイトル・質問・回答）"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <select
          className="admin-input"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">（カテゴリで絞り込み）</option>
          {categories.map((c) => (
            <option key={c.id} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
        <button className="admin-btn" type="submit">
          検索
        </button>
      </form>

      <details className="admin-tagfilter">
        <summary>タグで絞り込み{tagIds.length ? `（${tagIds.length}件選択中）` : ""}</summary>
        <TagPicker
          tags={tags}
          folders={folders}
          selectedIds={tagIds}
          onChange={setTagIds}
        />
      </details>

      {loading && <p className="admin-status">読み込み中...</p>}
      {error && <p className="admin-status admin-error">{error}</p>}

      <table className="admin-table">
        <thead>
          <tr>
            <th>タイトル</th>
            <th>カテゴリ</th>
            <th>タグ</th>
            <th className="admin-td-num">言い換え数</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((qa) => (
            <tr key={qa.id}>
              <td>{qa.title || "（無題）"}</td>
              <td>{qa.category ?? "－"}</td>
              <td>{qa.tags.length ? qa.tags.join(", ") : "－"}</td>
              <td className="admin-td-num">{qa.hiroba_question_altered_count}</td>
              <td className="admin-td-actions">
                <Link
                  className="admin-link"
                  to={`/admin/qa/${qa.id}?back=${backParam}`}
                >
                  編集
                </Link>
                <button
                  className="admin-btn admin-btn-danger admin-btn-sm"
                  type="button"
                  onClick={() => onDelete(qa.id)}
                  disabled={deletingId === qa.id}
                >
                  {deletingId === qa.id ? "削除中..." : "削除"}
                </button>
              </td>
            </tr>
          ))}
          {!loading && items.length === 0 && (
            <tr>
              <td colSpan={5} className="admin-muted">
                該当するQAがありません
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="admin-pager">
        <button
          className="admin-btn"
          disabled={offset === 0 || loading}
          onClick={() => load(offset - PAGE_SIZE)}
        >
          前へ
        </button>
        <span>
          {page} / {maxPage}（全 {total} 件）
        </span>
        <button
          className="admin-btn"
          disabled={offset + PAGE_SIZE >= total || loading}
          onClick={() => load(offset + PAGE_SIZE)}
        >
          次へ
        </button>
      </div>

      {/* CSV 一括インポート/エクスポートは画面下部にまとめて配置する */}
      <details className="admin-tagfilter admin-csv-tools">
        <summary>CSV 一括インポート / エクスポート</summary>
        <div className="admin-import">
          <p className="admin-hint">
            列: <code>uuid</code>（空=新規/既存=更新）, <code>title</code>,{" "}
            <code>question_text</code>, <code>answer_text</code>,{" "}
            <code>category_id</code>, <code>tags</code>（タグ名のカンマ区切り。
            存在しないタグ名は自動作成）。UTF-8 で保存してください。
          </p>
          <input ref={fileRef} type="file" accept=".csv" disabled={importing} />
          <button
            className="admin-btn admin-btn-primary"
            onClick={onImport}
            disabled={importing}
          >
            {importing ? "インポート中..." : "インポート"}
          </button>
          {importError && (
            <p className="admin-status admin-error">{importError}</p>
          )}
          {importResult && (
            <div className="admin-status">
              <p>
                成功 {importResult.success_count} 件 / 失敗{" "}
                {importResult.total - importResult.success_count} 件（全{" "}
                {importResult.total} 件）
              </p>
              {importResult.results.some((r) => r.status === "error") && (
                <ul className="admin-import-errors">
                  {importResult.results
                    .filter((r) => r.status === "error")
                    .map((r) => (
                      <li key={r.row}>
                        行 {r.row + 1}: {r.error}
                      </li>
                    ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
