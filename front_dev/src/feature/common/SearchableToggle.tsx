// 検索対象フラグ（is_searchable）の共通UI部品（ADR-0092 / ADR-0093）。
// QA一覧・言い換え質問文一覧・トラブルシューティング記事一覧の3画面で共有する。
// 新規UIライブラリは導入せず、素の <input type="checkbox"> に style.css のスイッチ外観を与える
// （ADR-0093 決定5）。

// 一覧の絞り込みセレクトの値（3値）。URLクエリ・APIの Optional<boolean> と相互変換する。
export type SearchableFilter = "all" | "true" | "false";

// URLクエリ（?is_searchable=true|false、既定「すべて」は省略, ADR-0093 決定7）→ 内部状態。
export function parseSearchableParam(value: string | null): SearchableFilter {
  return value === "true" || value === "false" ? value : "all";
}

// 内部状態 → API引数（undefined＝すべて）。
export function searchableFilterToParam(
  filter: SearchableFilter,
): boolean | undefined {
  if (filter === "all") return undefined;
  return filter === "true";
}

// 一覧の検索条件に置く3値セレクト。
export function SearchableFilterSelect({
  value,
  onChange,
}: {
  value: SearchableFilter;
  onChange: (next: SearchableFilter) => void;
}) {
  return (
    <select
      className="admin-input"
      aria-label="検索対象で絞り込み"
      value={value}
      onChange={(e) => onChange(e.target.value as SearchableFilter)}
    >
      <option value="all">（検索対象：すべて）</option>
      <option value="true">検索可のみ</option>
      <option value="false">検索不可のみ</option>
    </select>
  );
}

// 一覧の各行に置くトグル。押下で即時保存する（楽観的更新は呼び出し側が担う, ADR-0093 決定3）。
// 更新中は disabled にして、1行あたりの更新要求が同時に1つまでになるようにする。
export function SearchableToggle({
  checked,
  disabled,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  label?: string;
}) {
  return (
    <label className="admin-switch">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={label ?? "検索対象"}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="admin-switch-track" aria-hidden="true" />
      <span className="admin-switch-label">{checked ? "検索可" : "検索不可"}</span>
    </label>
  );
}
