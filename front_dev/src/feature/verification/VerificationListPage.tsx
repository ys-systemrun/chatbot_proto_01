import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  deleteVerificationQuestion,
  importVerificationQuestionsCsv,
  listVerificationQuestions,
  runVerification,
} from "../../api";
import type {
  VerificationImportResponse,
  VerificationQuestionSummary,
  VerificationRun,
} from "../../domain/admin/verification";

const PAGE_SIZE = 20;

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "未実行";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function evaluationLabel(run: VerificationRun | null): string {
  if (!run) return "－";
  if (run.evaluation === 1) return "適切";
  if (run.evaluation === 0) return "不適切";
  return "未評価";
}

/** 上位N件のタグ／情報源を "名前 (score)" のバッジ列で簡易表示する。 */
function topBadges(labels: string[], max = 3): string {
  if (labels.length === 0) return "－";
  const shown = labels.slice(0, max).join(", ");
  return labels.length > max ? `${shown} …(+${labels.length - max})` : shown;
}

export default function VerificationListPage() {
  const [items, setItems] = useState<VerificationQuestionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [keyword, setKeyword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);

  // CSV インポート状態
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] =
    useState<VerificationImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  function load(nextOffset: number) {
    setLoading(true);
    setError(null);
    listVerificationQuestions({
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

  async function onRun(id: number) {
    setRunningId(id);
    setError(null);
    try {
      await runVerification(id);
      load(offset); // 最新の実行結果を反映
    } catch (e) {
      setError(String(e));
    } finally {
      setRunningId(null);
    }
  }

  async function onDelete(id: number) {
    if (!window.confirm("この検証質問と全実行履歴を削除します。よろしいですか？")) {
      return;
    }
    setError(null);
    try {
      await deleteVerificationQuestion(id);
      load(offset);
    } catch (e) {
      setError(String(e));
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
      const result = await importVerificationQuestionsCsv(file);
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

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">検証質問一覧</h1>
        <Link className="admin-btn admin-btn-primary" to="/admin/verification/new">
          ＋ 新規質問登録
        </Link>
      </div>

      <form className="admin-filters" onSubmit={onSearch}>
        <input
          className="admin-input"
          placeholder="キーワード（質問文・メモ）"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <button className="admin-btn" type="submit">
          検索
        </button>
      </form>

      <details className="admin-tagfilter">
        <summary>CSV 一括インポート</summary>
        <div className="admin-import">
          <p className="admin-hint">
            列: <code>question_text</code>（必須）, <code>memo</code>（任意）。UTF-8
            で保存してください。常に新規追加されます（重複判定なし）。
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
            <th>質問文</th>
            <th>メモ</th>
            <th>既存タグ</th>
            {/* 追加（IMPL-202608261510 T7） */}
            <th>最終実行</th>
            <th>新規タグ</th>
            {/* 「選択タグ」から変更 */}
            <th>情報源</th>
            <th>評価</th>
            <th>状態</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((q) => {
            const run = q.latest_run;
            return (
              <tr key={q.id}>
                <td>
                  <Link className="admin-link" to={`/admin/verification/${q.id}`}>
                    {q.question_text.length > 40
                      ? q.question_text.slice(0, 40) + "…"
                      : q.question_text}
                  </Link>
                </td>
                <td>{q.memo || "－"}</td>
                <td>{topBadges(q.existing_tags)}</td>
                {/* 追加（IMPL-202608261510 T7）。topBadges は既存の共通関数を再利用 */}
                <td>{fmtDateTime(run?.executed_at)}</td>
                <td>
                  {run
                    ? topBadges(
                        run.tags.map(
                          (t) =>
                            `${t.tag_name}${
                              t.score != null ? ` (${t.score.toFixed(2)})` : ""
                            }`,
                        ),
                      )
                    : "－"}
                </td>
                <td>
                  {run
                    ? topBadges(
                        run.sources.map(
                          (s) =>
                            `${s.title ?? s.source_id ?? "?"}${
                              s.score != null ? ` (${s.score.toFixed(2)})` : ""
                            }`,
                        ),
                      )
                    : "－"}
                </td>
                <td>{evaluationLabel(run)}</td>
                <td>
                  {run ? (
                    <span
                      className={
                        run.status === "error" ? "admin-error" : undefined
                      }
                      title={run.error_message ?? undefined}
                    >
                      {run.status === "error" ? "エラー" : "成功"}
                    </span>
                  ) : (
                    "－"
                  )}
                </td>
                <td className="admin-actions">
                  <button
                    className="admin-btn"
                    disabled={runningId === q.id}
                    onClick={() => onRun(q.id)}
                  >
                    {runningId === q.id ? "実行中..." : "再実行"}
                  </button>
                  <Link className="admin-link" to={`/admin/verification/${q.id}`}>
                    詳細
                  </Link>
                  <button className="admin-btn" onClick={() => onDelete(q.id)}>
                    削除
                  </button>
                </td>
              </tr>
            );
          })}
          {!loading && items.length === 0 && (
            <tr>
              <td colSpan={9} className="admin-muted">
                検証質問がありません
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
