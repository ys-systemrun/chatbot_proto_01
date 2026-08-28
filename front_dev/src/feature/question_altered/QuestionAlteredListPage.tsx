import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  deleteQuestionAltered,
  downloadQuestionAlteredExport,
  importQuestionAlteredCsv,
  listQuestionAltered,
} from "../../api";
import type {
  QaAlteredImportResponse,
  QaAlteredItem,
} from "../../domain/admin/question_altered";
import { QaPicker } from "../common/QaPicker";

const PAGE_SIZE = 20;

// 言い換え質問文（is_primary=false）一覧ページ（IMPL-202608281100 / ADR-0064 要件6.1）。
// QaListPage のUIパターンを踏襲し、QAピッカー絞り込み・キーワード絞り込み・ページング・
// CSVインポート/エクスポート・行単位の削除を提供する。
export default function QuestionAlteredListPage() {
  const [items, setItems] = useState<QaAlteredItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);

  const [keyword, setKeyword] = useState("");
  const [qaId, setQaId] = useState("");
  const [qaLabel, setQaLabel] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] =
    useState<QaAlteredImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  function load(nextOffset: number) {
    setLoading(true);
    setError(null);
    listQuestionAltered({
      qa_id: qaId || undefined,
      keyword: keyword || undefined,
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
  }

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    load(0);
  }

  function clearQaFilter() {
    setQaId("");
    setQaLabel("");
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
      const result = await importQuestionAlteredCsv(file);
      setImportResult(result);
      if (fileRef.current) fileRef.current.value = "";
      load(0);
    } catch (e) {
      setImportError(String(e));
    } finally {
      setImporting(false);
    }
  }

  async function onExport() {
    setExporting(true);
    setError(null);
    try {
      await downloadQuestionAlteredExport();
    } catch (e) {
      setError(String(e));
    } finally {
      setExporting(false);
    }
  }

  async function onDelete(item: QaAlteredItem) {
    if (
      !window.confirm(
        `この言い換え質問文を削除しますか？\n\n「${item.text}」\n\nこの操作は取り消せません。`,
      )
    ) {
      return;
    }
    try {
      await deleteQuestionAltered(item.id);
      load(offset);
    } catch (e) {
      setError(String(e));
    }
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">言い換え質問文一覧</h1>
        <Link
          className="admin-btn admin-btn-primary"
          to="/admin/question_altered/new"
        >
          ＋ 新規言い換え
        </Link>
      </div>

      <p className="admin-muted">
        QAの言い換え質問文（パラフレーズ、is_primary=false）を管理します。主質問文（QA登録編集
        フォームが管理）は一覧に表示されません。
      </p>

      <form className="admin-filters" onSubmit={onSearch}>
        <input
          className="admin-input"
          placeholder="キーワード（言い換え文の部分一致）"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <button className="admin-btn" type="submit">
          検索
        </button>
        <button className="admin-btn" type="button" onClick={onExport} disabled={exporting}>
          {exporting ? "エクスポート中..." : "CSVエクスポート"}
        </button>
      </form>

      <details className="admin-tagfilter">
        <summary>
          対象QAで絞り込み{qaLabel ? `（${qaLabel}）` : ""}
        </summary>
        <div className="admin-import">
          {qaId ? (
            <p className="admin-status">
              絞り込み中: <strong>{qaLabel}</strong>{" "}
              <button className="admin-btn" type="button" onClick={clearQaFilter}>
                解除
              </button>
            </p>
          ) : (
            <QaPicker
              onSelect={(id, title) => {
                setQaId(id);
                setQaLabel(title);
              }}
            />
          )}
        </div>
      </details>

      <details className="admin-tagfilter">
        <summary>CSV 一括インポート</summary>
        <div className="admin-import">
          <p className="admin-hint">
            列: <code>id</code>（空=新規/既存=更新）, <code>qa_id</code>
            （新規時必須）, <code>text</code>（必須）, <code>is_primary</code>
            （入力は無視）。UTF-8 で保存してください。エクスポートしたCSVはそのまま再インポート
            できます。<code>id</code> が主質問文行（is_primary=true）を指す行はエラーになります。
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

      {loading && <p className="admin-status">読み込み中...</p>}
      {error && <p className="admin-status admin-error">{error}</p>}

      <table className="admin-table">
        <thead>
          <tr>
            <th>対象QA</th>
            <th>言い換え質問文</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.qa_title ?? "－"}</td>
              <td>{item.text}</td>
              <td>
                <Link
                  className="admin-link"
                  to={`/admin/question_altered/${item.id}`}
                >
                  編集
                </Link>{" "}
                <button
                  className="admin-link admin-link-danger"
                  type="button"
                  onClick={() => onDelete(item)}
                >
                  削除
                </button>
              </td>
            </tr>
          ))}
          {!loading && items.length === 0 && (
            <tr>
              <td colSpan={3} className="admin-muted">
                該当する言い換え質問文がありません
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
    </div>
  );
}
