// タグ検索・絞り込み／タグフォルダ別グルーピング／類似候補チェックの純粋ロジック
// （ADR-0070 / ADR-0071 / ADR-0072）。TagPicker・TagTreePage の双方から利用する。
// バックエンドAPIは追加せず、list_tags が取得済みの全件ツリーに対してクライアント側で計算する。

import type { TagFolder, TagNode } from "../../domain/admin/tag";

export interface FlatTag {
  node: TagNode;
  depth: number;
}

/** 全角・半角、大文字・小文字を正規化する（NFKC + 小文字化, ADR-0070/0071）。 */
export function normalizeTagText(s: string): string {
  return s.normalize("NFKC").toLowerCase();
}

/** タグ名またはエイリアスが query（正規化済み・部分一致）にマッチするか。 */
export function tagMatchesQuery(node: TagNode, normalizedQuery: string): boolean {
  if (!normalizedQuery) return true;
  if (normalizeTagText(node.name).includes(normalizedQuery)) return true;
  return node.aliases.some((a) =>
    normalizeTagText(a.alias).includes(normalizedQuery),
  );
}

export interface BreadcrumbMatch {
  node: TagNode;
  // ルート→自身の名前パス（パンくず表示用）。最後の要素が自身。
  path: string[];
}

/**
 * 絞り込み結果（ADR-0070）。タグ名・エイリアスに一致したタグを、ルートからのパンくず
 *（祖先名の経路）付きで返す。ヒットしないタグ・兄弟タグは含めない（祖先はパンくずで表現）。
 */
export function filterTagsWithBreadcrumb(
  tree: TagNode[],
  query: string,
): BreadcrumbMatch[] {
  const nq = normalizeTagText(query.trim());
  if (!nq) return [];
  const result: BreadcrumbMatch[] = [];
  function walk(node: TagNode, ancestors: string[]) {
    const path = [...ancestors, node.name];
    if (tagMatchesQuery(node, nq)) {
      result.push({ node, path });
    }
    for (const child of node.children ?? []) walk(child, path);
  }
  for (const root of tree) walk(root, []);
  return result;
}

export interface FlatFolder {
  folder: TagFolder;
  depth: number; // フォルダ階層のネスト深さ（0=ルートフォルダ）
  path: string[]; // ルート→自身のフォルダ名パス（パンくず表示用、最後の要素が自身）
}

/**
 * タグフォルダのツリー（ADR-0073）を深さ優先で平坦化し、各フォルダに階層深さと
 * ルートからのパンくずパス（フォルダ名の経路）を付けて返す。フォルダ名は重複しうるため
 * （ADR-0073 決定1）、プルダウン等の選択UIでは path を併記して同名フォルダを識別する。
 */
export function flattenFolders(folders: TagFolder[]): FlatFolder[] {
  const result: FlatFolder[] = [];
  function walk(folder: TagFolder, depth: number, ancestors: string[]) {
    const path = [...ancestors, folder.name];
    result.push({ folder, depth, path });
    for (const child of folder.children ?? []) walk(child, depth + 1, path);
  }
  for (const root of folders) walk(root, 0, []);
  return result;
}

/** フォルダのパンくずパス（フォルダ名の経路）を "親 › 子" 形式の文字列にする。 */
export function folderPathLabel(path: string[]): string {
  return path.join(" › ");
}

export interface FolderGroup {
  folderId: number | null;
  folderName: string | null; // null は「未分類」
  description: string | null;
  folderDepth: number; // フォルダ階層のネスト深さ（セクション見出しのインデント用、ADR-0073）
  path: string[]; // ルート→自身のフォルダ名パス（パンくず。「未分類」は空配列）
  items: FlatTag[]; // このフォルダに直接割り当てられたタグ（同一フォルダ内の is-a 深さ付き）
}

/**
 * predicate を満たすタグだけを、同一グループ内の祖先数を深さとして平坦化する。
 * タグフォルダ付与は parent_tag_id 階層と独立するため、親が別グループのタグは深さ0で現れる。
 */
function flattenForGroup(
  tree: TagNode[],
  predicate: (folderId: number | null) => boolean,
): FlatTag[] {
  const result: FlatTag[] = [];
  function walk(node: TagNode, ancestorsInGroup: number) {
    const inGroup = predicate(node.folder_id ?? null);
    if (inGroup) result.push({ node, depth: ancestorsInGroup });
    const next = ancestorsInGroup + (inGroup ? 1 : 0);
    for (const child of node.children ?? []) walk(child, next);
  }
  for (const root of tree) walk(root, 0);
  return result;
}

/**
 * タグをタグフォルダの階層（ADR-0073）ごとにグルーピングする。フォルダツリーを深さ優先
 *（親→子の順）で走査し、各フォルダをセクションとして folderDepth（インデント用）と
 * path（パンくず）付きで返す。各セクションには、そのフォルダに直接割り当てられたタグのみを
 * items として持たせる（見出しの直下タグ数 = items.length）。中間フォルダ自体にタグが無くても、
 * 子孫フォルダにタグがあれば見出しとして残し、階層構造を保つ。配下（自身・子孫）にタグが
 * まったく無いフォルダ枝は省く。最後に「未分類」（folder_id 未設定、または folders に含まれない
 * フォルダを指すタグ）を置く。
 */
export function groupTagsByFolder(
  tree: TagNode[],
  folders: TagFolder[],
): FolderGroup[] {
  const knownIds = new Set<number>();
  (function collect(fs: TagFolder[]) {
    for (const f of fs) {
      knownIds.add(f.id);
      collect(f.children ?? []);
    }
  })(folders);

  const groups: FolderGroup[] = [];

  function subtreeHasTags(folder: TagFolder): boolean {
    if (flattenForGroup(tree, (fid) => fid === folder.id).length > 0) return true;
    return (folder.children ?? []).some(subtreeHasTags);
  }

  function walk(folder: TagFolder, depth: number, ancestors: string[]) {
    if (!subtreeHasTags(folder)) return; // タグを一切含まない枝は省く
    const path = [...ancestors, folder.name];
    groups.push({
      folderId: folder.id,
      folderName: folder.name,
      description: folder.description,
      folderDepth: depth,
      path,
      items: flattenForGroup(tree, (fid) => fid === folder.id),
    });
    for (const child of folder.children ?? []) walk(child, depth + 1, path);
  }

  for (const root of folders) walk(root, 0, []);

  const uncategorized = flattenForGroup(
    tree,
    (fid) => fid === null || !knownIds.has(fid),
  );
  if (uncategorized.length > 0) {
    groups.push({
      folderId: null,
      folderName: null,
      description: null,
      folderDepth: 0,
      path: [],
      items: uncategorized,
    });
  }
  return groups;
}

/** Levenshtein 編集距離（挿入・削除・置換の最小回数）。 */
export function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  let curr = new Array<number>(b.length + 1);
  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[b.length];
}

export interface SimilarCandidate {
  node: TagNode;
  matchedText: string; // マッチした既存の名前 or エイリアス
  kind: "name" | "alias";
  reason: "substring" | "distance";
  parentName: string | null;
}

/**
 * 新規タグ作成時の類似候補チェック（ADR-0071・非ブロッキング）。入力名と既存タグ名・エイリアスを
 * 正規化した上で、部分文字列一致（双方向）または編集距離が threshold 以下のものを候補として返す。
 * 1タグにつき1件（最初に見つかった根拠）に集約する。作成自体はブロックしない。
 */
export function findSimilarTags(
  tree: TagNode[],
  input: string,
  threshold = 2,
): SimilarCandidate[] {
  const ni = normalizeTagText(input.trim());
  if (!ni) return [];

  // id -> 親タグ名 の対応を作る（所属階層の表示用）。
  const parentNameById = new Map<number, string | null>();
  function indexParents(node: TagNode, parentName: string | null) {
    parentNameById.set(node.id, parentName);
    for (const child of node.children ?? []) indexParents(child, node.name);
  }
  for (const root of tree) indexParents(root, null);

  const candidates: SimilarCandidate[] = [];
  function check(
    node: TagNode,
    text: string,
    kind: "name" | "alias",
  ): SimilarCandidate | null {
    const nt = normalizeTagText(text);
    if (!nt) return null;
    let reason: "substring" | "distance" | null = null;
    if (nt.includes(ni) || ni.includes(nt)) reason = "substring";
    else if (levenshtein(ni, nt) <= threshold) reason = "distance";
    if (!reason) return null;
    return {
      node,
      matchedText: text,
      kind,
      reason,
      parentName: parentNameById.get(node.id) ?? null,
    };
  }
  function walk(node: TagNode) {
    let found = check(node, node.name, "name");
    if (!found) {
      for (const a of node.aliases) {
        found = check(node, a.alias, "alias");
        if (found) break;
      }
    }
    if (found) candidates.push(found);
    for (const child of node.children ?? []) walk(child);
  }
  for (const root of tree) walk(root);
  return candidates;
}
