import type { TagNode } from "../../domain/admin/tag";

interface FlatTag {
  node: TagNode;
  depth: number;
}

function flatten(nodes: TagNode[], depth = 0, acc: FlatTag[] = []): FlatTag[] {
  for (const node of nodes) {
    acc.push({ node, depth });
    if (node.children?.length) flatten(node.children, depth + 1, acc);
  }
  return acc;
}

/**
 * タグ階層をインデント付きのチェックボックス一覧として表示する共通コンポーネント。
 * QA編集フォーム・タグ階層ページの双方から利用する（IMPL-202608060837 T20）。
 */
export function TagPicker({
  tags,
  selectedIds,
  onChange,
}: {
  tags: TagNode[];
  selectedIds: number[];
  onChange: (ids: number[]) => void;
}) {
  const flat = flatten(tags);
  const selected = new Set(selectedIds);

  function toggle(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange([...next]);
  }

  if (flat.length === 0) {
    return <p className="admin-muted">タグがありません</p>;
  }

  return (
    <div className="admin-tagpicker">
      {flat.map(({ node, depth }) => (
        <label
          key={node.id}
          className="admin-tagpicker-item"
          style={{ paddingLeft: `${depth * 1.2}rem` }}
        >
          <input
            type="checkbox"
            checked={selected.has(node.id)}
            onChange={() => toggle(node.id)}
          />
          <span>{node.name}</span>
        </label>
      ))}
    </div>
  );
}

export default TagPicker;
