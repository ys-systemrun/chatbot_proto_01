import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  createTag,
  deleteTag,
  downloadTagsExport,
  importTagsCsv,
  listTags,
  updateTag,
} from "../../api";
import type { TagImportResponse, TagNode } from "../../domain/admin/tag";

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

export default function TagTreePage() {
  const [tags, setTags] = useState<TagNode[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [newName, setNewName] = useState("");
  const [newParent, setNewParent] = useState<number | null>(null);
  const [newDesc, setNewDesc] = useState("");

  // CSV インポート状態（IMPL-202608261630 T5）
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<TagImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // CSV エクスポート状態（IMPL-202608281500 / ADR-0065）
  const [exporting, setExporting] = useState(false);

  function reload() {
    setLoading(true);
    listTags()
      .then(setTags)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(reload, []);

  const flat = flatten(tags);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    await run(() =>
      createTag({
        name: newName.trim(),
        parent_tag_id: newParent,
        description: newDesc.trim() || null,
      }),
    );
    setNewName("");
    setNewDesc("");
    setNewParent(null);
  }

  function onRename(node: TagNode) {
    const name = window.prompt("新しいタグ名", node.name);
    if (name == null || name.trim() === "" || name === node.name) return;
    run(() => updateTag(node.id, { name: name.trim() }));
  }

  function onEditDesc(node: TagNode) {
    const desc = window.prompt("説明文（空で消去）", node.description ?? "");
    if (desc == null) return;
    run(() => updateTag(node.id, { description: desc.trim() || null }));
  }

  function onMove(node: TagNode, parentValue: string) {
    const parent = parentValue === "" ? null : Number(parentValue);
    run(() => updateTag(node.id, { parent_tag_id: parent }));
  }

  function onDelete(node: TagNode) {
    if (!window.confirm(`タグ「${node.name}」を削除しますか？`)) return;
    run(() => deleteTag(node.id));
  }

  async function onExport() {
    setExporting(true);
    setError(null);
    try {
      await downloadTagsExport();
    } catch (e) {
      setError(String(e));
    } finally {
      setExporting(false);
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
      const result = await importTagsCsv(file);
      setImportResult(result);
      if (fileRef.current) fileRef.current.value = "";
      reload(); // 一覧を再取得
    } catch (e) {
      setImportError(String(e));
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">タグ階層</h1>
        <button
          className="admin-btn"
          type="button"
          onClick={onExport}
          disabled={exporting}
        >
          {exporting ? "エクスポート中..." : "CSVエクスポート"}
        </button>
      </div>

      {error && <p className="admin-status admin-error">{error}</p>}

      <form className="admin-tagcreate" onSubmit={onCreate}>
        <input
          className="admin-input"
          placeholder="新規タグ名"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <select
          className="admin-input"
          value={newParent ?? ""}
          onChange={(e) => setNewParent(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">（親なし＝ルート）</option>
          {flat.map(({ node, depth }) => (
            <option key={node.id} value={node.id}>
              {"　".repeat(depth) + node.name}
            </option>
          ))}
        </select>
        <input
          className="admin-input"
          placeholder="説明文（任意）"
          value={newDesc}
          onChange={(e) => setNewDesc(e.target.value)}
        />
        <button className="admin-btn admin-btn-primary" type="submit">
          追加
        </button>
      </form>

      <details className="admin-tagfilter">
        <summary>CSV 一括インポート</summary>
        <div className="admin-import">
          <p className="admin-hint">
            列: <code>name</code>（必須）, <code>parent_name</code>（任意、空欄は
            新規作成時＝ルート直下／更新時＝変更なし）, <code>description</code>
            （任意、空欄は更新時＝変更なし）。name が既存タグに一致すれば更新、
            一致しなければ新規作成します。UTF-8 で保存してください。
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

      <ul className="admin-taglist">
        {flat.map(({ node, depth }) => {
          const hasChildren = (node.children?.length ?? 0) > 0;
          return (
            <li
              key={node.id}
              className="admin-tagrow"
              style={{ paddingLeft: `${depth * 1.4}rem` }}
            >
              <div className="admin-tagrow-main">
                <span className="admin-tagname">{node.name}</span>
                {node.description && (
                  <span className="admin-tagdesc">{node.description}</span>
                )}
                {node.aliases.map((a) => (
                  <span key={a.id} className="admin-alias" title="同義語（表示のみ）">
                    {a.alias}
                  </span>
                ))}
              </div>
              <div className="admin-tagrow-actions">
                <button className="admin-link" onClick={() => onRename(node)}>
                  名称
                </button>
                <button className="admin-link" onClick={() => onEditDesc(node)}>
                  説明
                </button>
                <select
                  className="admin-input admin-move-select"
                  value={node.parent_tag_id ?? ""}
                  onChange={(e) => onMove(node, e.target.value)}
                  title="親タグを変更"
                >
                  <option value="">（ルート）</option>
                  {flat
                    .filter((f) => f.node.id !== node.id)
                    .map((f) => (
                      <option key={f.node.id} value={f.node.id}>
                        親: {f.node.name}
                      </option>
                    ))}
                </select>
                <button
                  className="admin-link admin-danger"
                  disabled={hasChildren}
                  title={
                    hasChildren
                      ? "子タグを持つため削除できません"
                      : "削除（QA紐付けがある場合は拒否されます）"
                  }
                  onClick={() => onDelete(node)}
                >
                  削除
                </button>
              </div>
            </li>
          );
        })}
        {!loading && flat.length === 0 && (
          <li className="admin-muted">タグがありません</li>
        )}
      </ul>
    </div>
  );
}
