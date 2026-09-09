import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  addTagAlias,
  createTag,
  createTagFolder,
  deleteTag,
  deleteTagFolder,
  downloadTagsExport,
  importTagsCsv,
  listTagFolders,
  listTags,
  moveTagFolder,
  removeTagAlias,
  reorderTag,
  reorderTagFolder,
  updateTag,
  updateTagAlias,
  updateTagFolder,
} from "../../api";
import type {
  TagAlias,
  TagFolder,
  TagImportResponse,
  TagNode,
} from "../../domain/admin/tag";
import {
  filterTagsWithBreadcrumb,
  findSimilarTags,
  flattenFolders,
  folderPathLabel,
  groupTagsByFolder,
} from "./tagFilter";

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

// 各ノードが兄弟集合（同じ親）内で先頭／末尾かを判定する（ADR-0074 の「↑/↓」ボタン境界）。
// バックエンドが display_order 順で返すため、children 配列の並びがそのまま表示順になる。
interface Boundary {
  first: boolean;
  last: boolean;
}

function computeTagBoundaries(
  nodes: TagNode[],
  acc: Map<number, Boundary> = new Map(),
): Map<number, Boundary> {
  nodes.forEach((n, i) => {
    acc.set(n.id, { first: i === 0, last: i === nodes.length - 1 });
    if (n.children?.length) computeTagBoundaries(n.children, acc);
  });
  return acc;
}

function computeFolderBoundaries(
  folders: TagFolder[],
  acc: Map<number, Boundary> = new Map(),
): Map<number, Boundary> {
  folders.forEach((f, i) => {
    acc.set(f.id, { first: i === 0, last: i === folders.length - 1 });
    if (f.children?.length) computeFolderBoundaries(f.children, acc);
  });
  return acc;
}

export default function TagTreePage() {
  const [tags, setTags] = useState<TagNode[]>([]);
  const [folders, setFolders] = useState<TagFolder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [newName, setNewName] = useState("");
  const [newParent, setNewParent] = useState<number | null>(null);
  const [newDesc, setNewDesc] = useState("");
  const [newFolder, setNewFolder] = useState<number | null>(null);

  // 検索・絞り込み（ADR-0070）
  const [query, setQuery] = useState("");

  // タグフォルダ作成フォーム（ADR-0072、ADR-0073 で親フォルダ指定を追加）
  const [newFolderName, setNewFolderName] = useState("");
  const [newFolderDesc, setNewFolderDesc] = useState("");
  const [newFolderParent, setNewFolderParent] = useState<number | null>(null);

  // CSV インポート状態（IMPL-202608261630 T5）
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<TagImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // CSV エクスポート状態（IMPL-202608281500 / ADR-0065）
  const [exporting, setExporting] = useState(false);

  // タグエイリアスのインライン追加・編集（ADR-0080）。1度に1つの入力欄のみを開く。
  // aliasId=null は「追加」、非nullは既存エイリアスの「編集」。value が類似候補チェックの入力になる。
  const [aliasEdit, setAliasEdit] = useState<{
    tagId: number;
    aliasId: number | null;
    value: string;
  } | null>(null);

  function reload() {
    setLoading(true);
    Promise.all([listTags(), listTagFolders()])
      .then(([t, f]) => {
        setTags(t);
        setFolders(f);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(reload, []);

  const flat = flatten(tags);
  const isFiltering = query.trim() !== "";
  const matches = useMemo(
    () => filterTagsWithBreadcrumb(tags, query),
    [tags, query],
  );
  const groups = useMemo(() => groupTagsByFolder(tags, folders), [tags, folders]);
  // タグフォルダを深さ優先で平坦化（プルダウン・移動UI・パンくず用, ADR-0073）。
  // フォルダ名は重複しうるため、選択UIには path（パンくず）を併記する。
  const flatFolders = useMemo(() => flattenFolders(folders), [folders]);
  // 兄弟集合内の先頭／末尾判定（「↑/↓」ボタンの無効化用, ADR-0074）
  const tagBoundaries = useMemo(() => computeTagBoundaries(tags), [tags]);
  const folderBoundaries = useMemo(
    () => computeFolderBoundaries(folders),
    [folders],
  );
  // 新規作成名の類似候補（非ブロッキング, ADR-0071）
  const similar = useMemo(() => findSimilarTags(tags, newName), [tags, newName]);
  // エイリアス追加・編集中の入力に対する類似候補（ADR-0082）。新規タグ作成と同じ findSimilarTags を
  // 再利用し、操作対象のタグ自身（同じタグへの別表記の追加は正常）は候補から除外する。
  const aliasSimilar = useMemo(() => {
    if (!aliasEdit || !aliasEdit.value.trim()) return [];
    return findSimilarTags(tags, aliasEdit.value).filter(
      (c) => c.node.id !== aliasEdit.tagId,
    );
  }, [tags, aliasEdit]);

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
        folder_id: newFolder,
      }),
    );
    setNewName("");
    setNewDesc("");
    setNewParent(null);
    setNewFolder(null);
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

  function onSetFolder(node: TagNode, folderValue: string) {
    const folder = folderValue === "" ? null : Number(folderValue);
    run(() => updateTag(node.id, { folder_id: folder }));
  }

  function onDelete(node: TagNode) {
    if (!window.confirm(`タグ「${node.name}」を削除しますか？`)) return;
    run(() => deleteTag(node.id));
  }

  // タグを兄弟集合内で1つ上／下へ並べ替える（ADR-0074）。先頭/末尾ではボタンを無効化しているため、
  // 通常ここに到達するのは移動可能なケースのみ（サーバ側も境界は No-Op）。
  function onReorder(node: TagNode, direction: "up" | "down") {
    run(() => reorderTag(node.id, { direction }));
  }

  // --- タグエイリアスの追加・編集・削除（ADR-0080） --- //
  // 追加・編集はインライン入力欄で行い、入力中は類似候補チェック（ADR-0082）を非ブロッキング表示する。
  function beginAddAlias(node: TagNode) {
    setAliasEdit({ tagId: node.id, aliasId: null, value: "" });
  }

  function beginEditAlias(node: TagNode, alias: TagAlias) {
    setAliasEdit({ tagId: node.id, aliasId: alias.id, value: alias.alias });
  }

  function cancelAliasEdit() {
    setAliasEdit(null);
  }

  async function submitAliasEdit() {
    if (!aliasEdit) return;
    const value = aliasEdit.value.trim();
    if (!value) return;
    const { tagId, aliasId } = aliasEdit;
    await run(() =>
      aliasId == null
        ? addTagAlias(tagId, { alias: value })
        : updateTagAlias(tagId, aliasId, { alias: value }),
    );
    setAliasEdit(null);
  }

  function onDeleteAlias(node: TagNode, alias: TagAlias) {
    if (!window.confirm(`エイリアス「${alias.alias}」を削除しますか？`)) return;
    run(() => removeTagAlias(node.id, alias.id));
  }

  // --- タグフォルダマスタ管理（ADR-0072） --- //
  async function onCreateFolder(e: FormEvent) {
    e.preventDefault();
    if (!newFolderName.trim()) return;
    await run(() =>
      createTagFolder({
        name: newFolderName.trim(),
        description: newFolderDesc.trim() || null,
        parent_folder_id: newFolderParent,
      }),
    );
    setNewFolderName("");
    setNewFolderDesc("");
    setNewFolderParent(null);
  }

  // タグフォルダの移動（親フォルダの付け替え, ADR-0073）。
  // 移動先が自分自身または子孫の場合はサーバが 409 で拒否する。
  function onMoveFolder(folder: TagFolder, parentValue: string) {
    const parent = parentValue === "" ? null : Number(parentValue);
    run(() => moveTagFolder(folder.id, { new_parent_folder_id: parent }));
  }

  function onRenameFolder(folder: TagFolder) {
    const name = window.prompt("新しいタグフォルダ名", folder.name);
    if (name == null || name.trim() === "" || name === folder.name) return;
    run(() => updateTagFolder(folder.id, { name: name.trim() }));
  }

  function onEditFolderDesc(folder: TagFolder) {
    const desc = window.prompt("説明文（空で消去）", folder.description ?? "");
    if (desc == null) return;
    run(() =>
      updateTagFolder(folder.id, {
        name: folder.name,
        description: desc.trim() || null,
      }),
    );
  }

  function onDeleteFolder(folder: TagFolder) {
    if (!window.confirm(`タグフォルダ「${folder.name}」を削除しますか？`)) return;
    run(() => deleteTagFolder(folder.id));
  }

  // タグフォルダを兄弟集合内で1つ上／下へ並べ替える（ADR-0074）。
  function onReorderFolder(folder: TagFolder, direction: "up" | "down") {
    run(() => reorderTagFolder(folder.id, { direction }));
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

  // タグ1行分の操作ボタン群（絞り込み時・フォルダ別表示の双方で共用）。
  function actions(node: TagNode) {
    const hasChildren = (node.children?.length ?? 0) > 0;
    const bound = tagBoundaries.get(node.id) ?? { first: true, last: true };
    return (
      <div className="admin-tagrow-actions">
        <button
          className="admin-link admin-reorder"
          disabled={bound.first}
          title="1つ上へ"
          onClick={() => onReorder(node, "up")}
        >
          ↑
        </button>
        <button
          className="admin-link admin-reorder"
          disabled={bound.last}
          title="1つ下へ"
          onClick={() => onReorder(node, "down")}
        >
          ↓
        </button>
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
        <select
          className="admin-input admin-move-select"
          value={node.folder_id ?? ""}
          onChange={(e) => onSetFolder(node, e.target.value)}
          title="タグフォルダを変更"
        >
          <option value="">（未分類）</option>
          {flatFolders.map(({ folder, path }) => (
            <option key={folder.id} value={folder.id}>
              📁 {folderPathLabel(path)}
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
    );
  }

  // タグ行のエイリアス欄（ADR-0080: 追加・編集・削除、ADR-0082: 入力中の類似候補チェック）。
  // 表示専用のバッジから、各バッジの編集（✎）・削除（✕）＋追加入力欄を備えたUIへ拡張する。
  function aliasArea(node: TagNode) {
    const editing = aliasEdit?.tagId === node.id ? aliasEdit : null;
    return (
      <div className="admin-alias-area">
        {node.aliases.map((a) =>
          editing?.aliasId === a.id ? null : (
            <span key={a.id} className="admin-alias" title="同義語">
              {a.alias}
              <button
                type="button"
                className="admin-alias-btn"
                title="エイリアスを編集"
                onClick={() => beginEditAlias(node, a)}
              >
                ✎
              </button>
              <button
                type="button"
                className="admin-alias-btn admin-danger"
                title="エイリアスを削除"
                onClick={() => onDeleteAlias(node, a)}
              >
                ✕
              </button>
            </span>
          ),
        )}
        {editing ? (
          <span className="admin-alias-editor">
            <input
              className="admin-input admin-alias-input"
              autoFocus
              placeholder={
                editing.aliasId == null
                  ? "追加するエイリアス"
                  : "エイリアスを編集"
              }
              value={editing.value}
              onChange={(e) =>
                setAliasEdit({ ...editing, value: e.target.value })
              }
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  submitAliasEdit();
                } else if (e.key === "Escape") {
                  cancelAliasEdit();
                }
              }}
            />
            <button
              type="button"
              className="admin-link"
              onClick={submitAliasEdit}
              disabled={!editing.value.trim()}
            >
              保存
            </button>
            <button
              type="button"
              className="admin-link"
              onClick={cancelAliasEdit}
            >
              取消
            </button>
          </span>
        ) : (
          <button
            type="button"
            className="admin-link admin-alias-add"
            title="エイリアス（同義語）を追加"
            onClick={() => beginAddAlias(node)}
          >
            ＋エイリアス
          </button>
        )}
        {/* 入力中の類似候補（非ブロッキング, ADR-0082）。対象タグ自身は除外済み。 */}
        {editing && aliasSimilar.length > 0 && (
          <div className="admin-similar admin-alias-similar">
            <p className="admin-similar-head">
              似た名前の既存タグ・エイリアスがあります（登録はブロックしません。
              別概念なら続行、同じ概念なら既存をご利用ください）:
            </p>
            <ul className="admin-similar-list">
              {aliasSimilar.map((c) => (
                <li key={c.node.id}>
                  <span className="admin-tagname">{c.matchedText}</span>
                  {c.kind === "alias" && (
                    <span className="admin-alias">
                      エイリアス → {c.node.name}
                    </span>
                  )}
                  {c.parentName && (
                    <span className="admin-tagdesc">（親: {c.parentName}）</span>
                  )}
                  {c.node.description && (
                    <span className="admin-tagdesc">{c.node.description}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  // ancestors を渡すと先頭にパンくず（祖先名の経路）を表示する（絞り込み時, ADR-0070）。
  function tagMain(node: TagNode, ancestors?: string[]) {
    return (
      <div className="admin-tagrow-main">
        {ancestors && ancestors.length > 0 && (
          <span className="admin-breadcrumb">
            {ancestors.map((p, i) => (
              <span key={i} className="admin-breadcrumb-anc">
                {p} ›{" "}
              </span>
            ))}
          </span>
        )}
        <span className="admin-tagname">{node.name}</span>
        {node.description && (
          <span className="admin-tagdesc">{node.description}</span>
        )}
        {aliasArea(node)}
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">タグ階層</h1>
      </div>

      {error && <p className="admin-status admin-error">{error}</p>}

      {/* タグフォルダマスタ管理（ADR-0072 で新設、ADR-0073 で階層化・移動） */}
      <details className="admin-tagfilter">
        <summary>タグフォルダの管理</summary>
        <p className="admin-hint">
          タグフォルダは「対象システム」「動作環境」等の分類軸で、タグの親子階層（is-a）とは
          独立した表示専用の区分です。フォルダ同士を入れ子（親子）にできます（ADR-0073）。
          同名フォルダも作成でき、区別のため経路（親 › 子）を併記します。検索結果・スコアには
          影響しません。
        </p>
        <form className="admin-tagcreate" onSubmit={onCreateFolder}>
          <input
            className="admin-input"
            placeholder="新規タグフォルダ名"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
          />
          <select
            className="admin-input"
            value={newFolderParent ?? ""}
            onChange={(e) =>
              setNewFolderParent(e.target.value ? Number(e.target.value) : null)
            }
            title="親フォルダ（任意）"
          >
            <option value="">（親なし＝ルート）</option>
            {flatFolders.map(({ folder, path }) => (
              <option key={folder.id} value={folder.id}>
                📁 {folderPathLabel(path)}
              </option>
            ))}
          </select>
          <input
            className="admin-input"
            placeholder="説明文（任意）"
            value={newFolderDesc}
            onChange={(e) => setNewFolderDesc(e.target.value)}
          />
          <button className="admin-btn admin-btn-primary" type="submit">
            フォルダ追加
          </button>
        </form>
        <ul className="admin-taglist">
          {flatFolders.map(({ folder: f, depth, path }) => (
            <li
              key={f.id}
              className="admin-tagrow"
              style={{ paddingLeft: `${depth * 1.4}rem` }}
            >
              <div className="admin-tagrow-main">
                <span className="admin-tagname" title={folderPathLabel(path)}>
                  📁 {f.name}
                </span>
                {f.description && (
                  <span className="admin-tagdesc">{f.description}</span>
                )}
              </div>
              <div className="admin-tagrow-actions">
                <button
                  className="admin-link admin-reorder"
                  disabled={(folderBoundaries.get(f.id) ?? { first: true }).first}
                  title="1つ上へ"
                  onClick={() => onReorderFolder(f, "up")}
                >
                  ↑
                </button>
                <button
                  className="admin-link admin-reorder"
                  disabled={(folderBoundaries.get(f.id) ?? { last: true }).last}
                  title="1つ下へ"
                  onClick={() => onReorderFolder(f, "down")}
                >
                  ↓
                </button>
                <button className="admin-link" onClick={() => onRenameFolder(f)}>
                  名称
                </button>
                <button
                  className="admin-link"
                  onClick={() => onEditFolderDesc(f)}
                >
                  説明
                </button>
                <select
                  className="admin-input admin-move-select"
                  value={f.parent_folder_id ?? ""}
                  onChange={(e) => onMoveFolder(f, e.target.value)}
                  title="親フォルダを変更（移動）"
                >
                  <option value="">（ルート）</option>
                  {flatFolders
                    .filter((o) => o.folder.id !== f.id)
                    .map(({ folder, path: p }) => (
                      <option key={folder.id} value={folder.id}>
                        親: {folderPathLabel(p)}
                      </option>
                    ))}
                </select>
                <button
                  className="admin-link admin-danger"
                  title="タグから参照されている場合は拒否されます。子フォルダは親（祖父母）へ繰り上がります。"
                  onClick={() => onDeleteFolder(f)}
                >
                  削除
                </button>
              </div>
            </li>
          ))}
          {flatFolders.length === 0 && (
            <li className="admin-muted">タグフォルダがありません</li>
          )}
        </ul>
      </details>

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
        <select
          className="admin-input"
          value={newFolder ?? ""}
          onChange={(e) => setNewFolder(e.target.value ? Number(e.target.value) : null)}
          title="タグフォルダ（任意）"
        >
          <option value="">（未分類）</option>
          {flatFolders.map(({ folder, path }) => (
            <option key={folder.id} value={folder.id}>
              📁 {folderPathLabel(path)}
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

      {/* 類似候補の非ブロッキング警告（ADR-0071） */}
      {similar.length > 0 && (
        <div className="admin-similar">
          <p className="admin-similar-head">
            似た名前の既存タグ・エイリアスがあります（作成はブロックしません。
            別概念なら続行、同じ概念なら既存タグをご利用ください）:
          </p>
          <ul className="admin-similar-list">
            {similar.map((c) => (
              <li key={c.node.id}>
                <span className="admin-tagname">{c.matchedText}</span>
                {c.kind === "alias" && (
                  <span className="admin-alias">エイリアス → {c.node.name}</span>
                )}
                {c.parentName && (
                  <span className="admin-tagdesc">（親: {c.parentName}）</span>
                )}
                {c.node.description && (
                  <span className="admin-tagdesc">{c.node.description}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <input
        className="admin-input admin-tagsearch"
        type="search"
        placeholder="タグ名・エイリアスで絞り込み"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      {loading && <p className="admin-status">読み込み中...</p>}

      {/* 絞り込み時: パンくず付きのフラット一覧（ADR-0070） */}
      {isFiltering ? (
        <ul className="admin-taglist">
          {matches.map(({ node, path }) => (
            <li key={node.id} className="admin-tagrow">
              {tagMain(node, path.slice(0, -1))}
              {actions(node)}
            </li>
          ))}
          {!loading && matches.length === 0 && (
            <li className="admin-muted">一致するタグがありません</li>
          )}
        </ul>
      ) : (
        /* 未絞り込み時: タグフォルダ階層別セクション＋タグ階層インデント（ADR-0072/0073） */
        <div className="admin-folder-groups">
          {groups.map((g) => (
            <div key={g.folderId ?? "__none__"} className="admin-folder-group">
              <div
                className="admin-folder-heading"
                style={{ paddingLeft: `${g.folderDepth * 1.4}rem` }}
                title={g.path.length > 0 ? folderPathLabel(g.path) : undefined}
              >
                {g.folderName ?? "未分類"}
                <span className="admin-folder-count">（{g.items.length}）</span>
                {g.description && (
                  <span className="admin-tagdesc">{g.description}</span>
                )}
              </div>
              <ul className="admin-taglist">
                {g.items.map(({ node, depth }) => (
                  <li
                    key={node.id}
                    className="admin-tagrow"
                    style={{
                      paddingLeft: `${(g.folderDepth + depth + 1) * 1.4}rem`,
                    }}
                  >
                    {tagMain(node)}
                    {actions(node)}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {!loading && flat.length === 0 && (
            <p className="admin-muted">タグがありません</p>
          )}
        </div>
      )}

      {/* CSV 一括インポート/エクスポートは画面下部にまとめて配置する */}
      <details className="admin-tagfilter admin-csv-tools">
        <summary>CSV 一括インポート / エクスポート</summary>
        <div className="admin-import">
          <p className="admin-hint">
            列: <code>name</code>（必須）, <code>parent_name</code>（任意、空欄は
            新規作成時＝ルート直下／更新時＝変更なし）, <code>description</code>
            （任意、空欄は更新時＝変更なし）, <code>aliases</code>（任意、パイプ
            <code>|</code> 区切りで複数指定）。name が既存タグに一致すれば更新、
            一致しなければ新規作成します。UTF-8 で保存してください。
            <br />
            エイリアスは<strong>追加専用</strong>です（CSV に書いた同義語を対象タグへ
            追加するのみ。CSV から省いた既存エイリアスは削除されません）。別のタグに
            既に登録済みの同義語は、その1件のみ警告となり他は続行します（ADR-0081）。
            （タグフォルダはCSV対象外のため、管理画面で個別に設定してください。）
          </p>
          <div className="admin-csv-actions">
            <button
              className="admin-btn"
              type="button"
              onClick={onExport}
              disabled={exporting}
            >
              {exporting ? "エクスポート中..." : "CSVエクスポート"}
            </button>
          </div>
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
              {/* エイリアス追加専用の警告（別タグに既存 等, ADR-0081 決定3）。行自体は成功。 */}
              {importResult.results.some(
                (r) => (r.alias_warnings?.length ?? 0) > 0,
              ) && (
                <ul className="admin-import-warnings">
                  {importResult.results
                    .filter((r) => (r.alias_warnings?.length ?? 0) > 0)
                    .map((r) => (
                      <li key={r.row}>
                        行 {r.row + 1}（エイリアス警告）:{" "}
                        {r.alias_warnings!.join(" / ")}
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
