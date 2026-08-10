import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { listCategories, listQa, listTags } from "../../api";
import type { Category, QaSummary } from "../../domain/admin/qa";
import type { TagNode } from "../../domain/admin/tag";
import { TagPicker } from "../tag_admin/TagPicker";

const PAGE_SIZE = 20;

export default function QaListPage() {
  const [items, setItems] = useState<QaSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);

  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("");
  const [tagIds, setTagIds] = useState<number[]>([]);

  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<TagNode[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // フィルタ用のカテゴリ・タグを初回に取得する
  useEffect(() => {
    listCategories().then(setCategories).catch((e) => setError(String(e)));
    listTags().then(setTags).catch((e) => setError(String(e)));
  }, []);

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
  }

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    load(0);
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">QA一覧</h1>
        <Link className="admin-btn admin-btn-primary" to="/admin/qa/new">
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
        <TagPicker tags={tags} selectedIds={tagIds} onChange={setTagIds} />
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
              <td className="admin-td-num">{qa.question_altered_count}</td>
              <td>
                <Link className="admin-link" to={`/admin/qa/${qa.id}`}>
                  編集
                </Link>
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
    </div>
  );
}
