import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import {
  listTagFolders,
  listTags,
  listTroubleshootingArticles,
  listTroubleshootingSourceKeys,
} from "../../api";
import type { TroubleshootingSummary } from "../../domain/admin/troubleshooting";
import type { TagFolder, TagNode } from "../../domain/admin/tag";
import { TagPicker } from "../tag_admin/TagPicker";

const PAGE_SIZE = 20;

// URL の page（1始まり）を内部 offset（0始まり）へ変換する。不正値・未指定は先頭ページ扱い。
function pageParamToOffset(pageParam: string | null): number {
  const page = Number(pageParam);
  if (!Number.isInteger(page) || page < 1) return 0;
  return (page - 1) * PAGE_SIZE;
}

export default function TroubleshootingListPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const [items, setItems] = useState<TroubleshootingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(() =>
    pageParamToOffset(searchParams.get("page")),
  );

  const [keyword, setKeyword] = useState(() => searchParams.get("keyword") ?? "");
  const [sourceKey, setSourceKey] = useState(
    () => searchParams.get("source_key") ?? "",
  );
  const [tagIds, setTagIds] = useState<number[]>(() =>
    searchParams
      .getAll("tag_id")
      .map((v) => Number(v))
      .filter((n) => Number.isInteger(n) && n > 0),
  );

  const [sourceKeys, setSourceKeys] = useState<string[]>([]);
  const [tags, setTags] = useState<TagNode[]>([]);
  const [folders, setFolders] = useState<TagFolder[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // フィルタ用の出自・タグを初回に取得する
  useEffect(() => {
    listTroubleshootingSourceKeys()
      .then(setSourceKeys)
      .catch((e) => setError(String(e)));
    listTags().then(setTags).catch((e) => setError(String(e)));
    listTagFolders().then(setFolders).catch((e) => setError(String(e)));
  }, []);

  function syncUrl(nextOffset: number) {
    const next = new URLSearchParams();
    if (keyword) next.set("keyword", keyword);
    if (sourceKey) next.set("source_key", sourceKey);
    tagIds.forEach((id) => next.append("tag_id", String(id)));
    const page = Math.floor(nextOffset / PAGE_SIZE) + 1;
    if (page > 1) next.set("page", String(page));
    setSearchParams(next, { replace: true });
  }

  function load(nextOffset: number) {
    setLoading(true);
    setError(null);
    listTroubleshootingArticles({
      keyword: keyword || undefined,
      source_key: sourceKey || undefined,
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

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // 編集ページへ現在の一覧 URL（検索条件・ページ位置）を back として引き継ぐ（ADR-0068）。
  const backParam = encodeURIComponent(location.pathname + location.search);

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">トラブルシューティング記事一覧</h1>
      </div>

      <form className="admin-filters" onSubmit={onSearch}>
        <input
          className="admin-input"
          placeholder="キーワード（タイトル・現象・案内内容）"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <select
          className="admin-input"
          value={sourceKey}
          onChange={(e) => setSourceKey(e.target.value)}
        >
          <option value="">（出自で絞り込み）</option>
          {sourceKeys.map((sk) => (
            <option key={sk} value={sk}>
              {sk}
            </option>
          ))}
        </select>
        <button className="admin-btn" type="submit">
          検索
        </button>
      </form>

      <details className="admin-tagfilter">
        <summary>
          タグで絞り込み{tagIds.length ? `（${tagIds.length}件選択中）` : ""}
        </summary>
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
            <th>サブ見出し</th>
            <th>出自</th>
            <th>タグ</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id}>
              <td>{a.title || "（無題）"}</td>
              <td>{a.subtitle ?? "－"}</td>
              <td>{a.source_key}</td>
              <td>{a.tags.length ? a.tags.join(", ") : "－"}</td>
              <td className="admin-td-actions">
                <Link
                  className="admin-link"
                  to={`/admin/troubleshooting/${a.id}?back=${backParam}`}
                >
                  編集
                </Link>
              </td>
            </tr>
          ))}
          {!loading && items.length === 0 && (
            <tr>
              <td colSpan={5} className="admin-muted">
                該当する記事がありません
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
