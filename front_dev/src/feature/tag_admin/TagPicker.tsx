import { useMemo, useState } from "react";
import type { TagFolder, TagNode } from "../../domain/admin/tag";
import {
  filterTagsWithBreadcrumb,
  folderPathLabel,
  groupTagsByFolder,
} from "./tagFilter";

/**
 * タグ階層をチェックボックス一覧として表示する共通コンポーネント。
 * QA編集フォーム・タグ階層ページの双方から利用する（IMPL-202608060837 T20）。
 *
 * - フリーテキスト検索（タグ名・エイリアス部分一致, ADR-0070）。絞り込み中は一致タグを
 *   祖先パンくず付きで表示する。
 * - 未絞り込み時はタグフォルダ別セクション＋階層インデントで表示する（ADR-0072）。
 */
export function TagPicker({
  tags,
  folders = [],
  selectedIds,
  onChange,
}: {
  tags: TagNode[];
  folders?: TagFolder[];
  selectedIds: number[];
  onChange: (ids: number[]) => void;
}) {
  const [query, setQuery] = useState("");
  const selected = new Set(selectedIds);

  const matches = useMemo(
    () => filterTagsWithBreadcrumb(tags, query),
    [tags, query],
  );
  const groups = useMemo(
    () => groupTagsByFolder(tags, folders),
    [tags, folders],
  );

  function toggle(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange([...next]);
  }

  const isFiltering = query.trim() !== "";
  const hasAnyTag = groups.some((g) => g.items.length > 0);

  function checkbox(node: TagNode) {
    return (
      <input
        type="checkbox"
        checked={selected.has(node.id)}
        onChange={() => toggle(node.id)}
      />
    );
  }

  return (
    <div className="admin-tagpicker-wrap">
      <input
        className="admin-input admin-tagpicker-search"
        type="search"
        placeholder="タグ名・エイリアスで絞り込み"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      <div className="admin-tagpicker">
        {!hasAnyTag && <p className="admin-muted">タグがありません</p>}

        {hasAnyTag && isFiltering && (
          <>
            {matches.length === 0 && (
              <p className="admin-muted">一致するタグがありません</p>
            )}
            {matches.map(({ node, path }) => (
              <label key={node.id} className="admin-tagpicker-item">
                {checkbox(node)}
                <span className="admin-breadcrumb">
                  {path.slice(0, -1).map((p, i) => (
                    <span key={i} className="admin-breadcrumb-anc">
                      {p} ›{" "}
                    </span>
                  ))}
                  {node.name}
                </span>
              </label>
            ))}
          </>
        )}

        {hasAnyTag &&
          !isFiltering &&
          groups.map((g) => (
            <div key={g.folderId ?? "__none__"} className="admin-folder-group">
              <div
                className="admin-folder-heading"
                style={{ paddingLeft: `${g.folderDepth * 1.2}rem` }}
                title={g.path.length > 0 ? folderPathLabel(g.path) : undefined}
              >
                {g.folderName ?? "未分類"}
                <span className="admin-folder-count">（{g.items.length}）</span>
              </div>
              {g.items.map(({ node, depth }) => (
                <label
                  key={node.id}
                  className="admin-tagpicker-item"
                  style={{
                    paddingLeft: `${(g.folderDepth + depth + 1) * 1.2}rem`,
                  }}
                >
                  {checkbox(node)}
                  <span>{node.name}</span>
                </label>
              ))}
            </div>
          ))}
      </div>
    </div>
  );
}

export default TagPicker;
