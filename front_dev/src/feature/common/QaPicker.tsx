import { useEffect, useRef, useState } from "react";
import { listQa } from "../../api";
import type { QaSummary } from "../../domain/admin/qa";

/**
 * QA 検索ピッカー（IMPL-202608281100 T6 / ADR-0064 要件6.3）。
 *
 * キーワード（タイトル・質問文の部分一致）で既存 GET /api/qa を呼び出し、候補を絞り込んで
 * qa_id を選択する共通コンポーネント。TagPicker と同格の位置付けで、言い換え行の新規作成・
 * 一覧絞り込みから利用する。新規エンドポイントは追加しない。
 */
export function QaPicker({
  onSelect,
  placeholder = "QAのタイトル・質問文で検索",
}: {
  onSelect: (qaId: string, title: string) => void;
  placeholder?: string;
}) {
  const [keyword, setKeyword] = useState("");
  const [candidates, setCandidates] = useState<QaSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  // 入力中の過剰なリクエストを避けるためデバウンスする（約300ms）。
  useEffect(() => {
    const kw = keyword.trim();
    if (!kw) {
      setCandidates([]);
      return;
    }
    setLoading(true);
    setError(null);
    const timer = setTimeout(() => {
      listQa({ keyword: kw, limit: 10 })
        .then((res) => {
          setCandidates(res.items);
          setOpen(true);
        })
        .catch((e) => setError(String(e)))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [keyword]);

  function pick(qa: QaSummary) {
    onSelect(qa.id, qa.title || "（無題）");
    setKeyword("");
    setCandidates([]);
    setOpen(false);
  }

  return (
    <div className="admin-qapicker">
      <input
        className="admin-input"
        value={keyword}
        placeholder={placeholder}
        onChange={(e) => setKeyword(e.target.value)}
        onFocus={() => candidates.length > 0 && setOpen(true)}
      />
      {loading && <p className="admin-status">検索中...</p>}
      {error && <p className="admin-status admin-error">{error}</p>}
      {open && candidates.length > 0 && (
        <ul className="admin-qapicker-list">
          {candidates.map((qa) => (
            <li key={qa.id}>
              <button
                type="button"
                className="admin-qapicker-item"
                onClick={() => pick(qa)}
              >
                <span className="admin-qapicker-title">
                  {qa.title || "（無題）"}
                </span>
                {qa.category && (
                  <span className="admin-qapicker-cat">{qa.category}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && !loading && keyword.trim() && candidates.length === 0 && (
        <p className="admin-muted">該当するQAがありません</p>
      )}
    </div>
  );
}

export default QaPicker;
