import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getEvaluatedMessages } from "../../api";
import type { EvaluatedConversation, EvaluatedMessage, Release } from "../../domain/evaluated";

/**
 * 列の定義（見出し・既定幅・最小幅）。REQ-202609141030 6.4節の表に対応する（ADR-0087 決定4）。
 * 配列の順序が <colgroup> の <col> と <th> の順序に一致している必要がある。
 * 列構成（列数・意味・順序）を変更する場合は STORAGE_KEY のバージョンも上げること（ADR-0087 決定6）。
 */
const COLUMNS = [
  { label: "#", defaultWidth: 40, minWidth: 32 },
  { label: "役割", defaultWidth: 72, minWidth: 48 },
  { label: "評価", defaultWidth: 56, minWidth: 40 },
  // ADR-0099 §1・§4: 評価の理由・回答方式・リリース
  { label: "理由", defaultWidth: 200, minWidth: 80 },
  { label: "方式", defaultWidth: 80, minWidth: 56 },
  { label: "リリース", defaultWidth: 120, minWidth: 80 },
  { label: "モデル", defaultWidth: 140, minWidth: 80 },
  { label: "本文", defaultWidth: 320, minWidth: 120 },
  { label: "LLM 入力", defaultWidth: 260, minWidth: 120 },
  { label: "登録日時", defaultWidth: 130, minWidth: 100 },
] as const;

/** 見出しセルへ付与する既存クラス（幅以外の見た目: 文字揃え・色・フォント）。 */
const TH_CLASSES = [
  "ev-th ev-td-num",
  "ev-th",
  "ev-th ev-td-center",
  "ev-th",
  "ev-th ev-td-center",
  "ev-th ev-td-model",
  "ev-th ev-td-model",
  "ev-th",
  "ev-th",
  "ev-th ev-td-date",
] as const;

/** 列幅の localStorage キー（ADR-0087 決定6。列構成を変えるときは _v2 …と上げる）。
 * v2: ADR-0099 で「理由・方式・リリース」の3列を追加。 */
const STORAGE_KEY = "ev_column_widths_v2";

const defaultWidths = (): number[] => COLUMNS.map((c) => c.defaultWidth);

/**
 * localStorage から列幅を読み込む（REQ 6.3）。
 * (a) JSON 配列としてパース可能 (b) 要素数が列数と一致 (c) 全要素が有限の数値かつ対応する列の最小幅以上、
 * のすべてを満たす場合のみ採用し、それ以外は既定幅へフォールバックする。
 */
function loadWidths(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultWidths();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length !== COLUMNS.length) return defaultWidths();
    const widths = parsed.map((v) => Number(v));
    const valid = widths.every(
      (w, i) => Number.isFinite(w) && w >= COLUMNS[i].minWidth,
    );
    return valid ? widths : defaultWidths();
  } catch {
    // JSON 破損・localStorage 参照不可（プライベートモード等）でも画面をエラーにしない。
    return defaultWidths();
  }
}

/** 確定した列幅を保存する（ドラッグ終了時・リセット時のみ。mousemove では呼ばない, REQ 6.3）。 */
function saveWidths(widths: number[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(widths));
  } catch {
    // 保存できなくても表示は継続する（保存はあくまで利便性のため）。
  }
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function ExpandableCell({ text, className }: { text: string | null; className: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!text) return <td className={className}>－</td>;
  return (
    <td className={className}>
      <span className={expanded ? "" : "ev-input-truncate"}>{text}</span>
      <button className="ev-expand-btn" onClick={() => setExpanded((v) => !v)}>
        {expanded ? "折りたたむ" : "展開"}
      </button>
    </td>
  );
}

const ASK_MODE_LABELS: Record<string, string> = {
  pipeline: "パイプライン",
  agentic: "エージェント",
};

/** リリースの詳細（ホバーで表示）。release テーブル未登録なら ID のみ。 */
function releaseTitle(msg: EvaluatedMessage): string {
  const r = msg.release;
  if (!r) return msg.release_id ? `${msg.release_id}（詳細未登録）` : "";
  return [
    `release: ${r.release_id}`,
    `commit: ${r.git_commit ?? "不明"}${r.git_dirty ? "（未コミット変更あり）" : ""}`,
    `prompt: ${r.prompt_hash ?? "不明"}`,
    `chat model: ${r.chat_model_id ?? "不明"}`,
    `embedding: ${r.embedding_model_id ?? "不明"}`,
    `params: ${r.params ? JSON.stringify(r.params) : "不明"}`,
    `初回: ${r.first_seen_at ? formatDate(r.first_seen_at) : "不明"}`,
  ].join("\n");
}

function MessageRow({ msg }: { msg: EvaluatedMessage }) {
  const roleLabel = msg.role === 1 ? "ユーザー" : "アシスタント";
  const evalLabel = msg.evaluation === 1 ? "👍" : msg.evaluation === 2 ? "👎" : "－";
  const modeLabel = msg.ask_mode ? ASK_MODE_LABELS[msg.ask_mode] ?? msg.ask_mode : "－";

  return (
    <tr className={`ev-row ev-role-${msg.role === 1 ? "user" : "assistant"}`}>
      <td className="ev-td ev-td-num">{msg.order}</td>
      <td className="ev-td">{roleLabel}</td>
      <td className="ev-td ev-td-center">{evalLabel}</td>
      <td className="ev-td ev-td-comment">{msg.evaluation_comment ?? "－"}</td>
      <td className="ev-td ev-td-center">{modeLabel}</td>
      <td className="ev-td ev-td-model" title={releaseTitle(msg)}>
        {msg.release_id ? msg.release_id.slice(0, 8) : "－"}
      </td>
      <td className="ev-td ev-td-model">{msg.model ?? "－"}</td>
      <ExpandableCell text={msg.content} className="ev-td ev-td-content" />
      <ExpandableCell text={msg.input} className="ev-td ev-td-input" />
      <td className="ev-td ev-td-date">{formatDate(msg.created_at)}</td>
    </tr>
  );
}

type ResizeHandlers = {
  /** ドラッグ中のリアルタイム更新（親 state を更新＝画面内の全テーブルへ即時反映, ADR-0087 決定1）。 */
  onResize: (index: number, width: number) => void;
  /** mouseup。この時点の列幅を localStorage へ保存する。 */
  onResizeEnd: () => void;
  /** ドラッグハンドルのダブルクリック。対象列のみ既定幅へ戻す（REQ 6.5）。 */
  onResetColumn: (index: number) => void;
};

/**
 * 列見出しセル。右端にドラッグハンドルを持つ（ADR-0087 決定3）。
 * mousemove / mouseup は th ではなく window に登録し、マウスがハンドル領域から外れても
 * ドラッグを継続できるようにする。
 */
function ColumnHeader({
  index,
  width,
  handlers,
}: {
  index: number;
  width: number;
  handlers: ResizeHandlers;
}) {
  const [dragging, setDragging] = useState(false);
  const { onResize, onResizeEnd, onResetColumn } = handlers;

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startWidth = width;
    setDragging(true);
    // ドラッグ中のテキスト誤選択を防ぐ（REQ 6.1）。
    document.body.classList.add("ev-resizing");

    const handleMove = (ev: MouseEvent) => {
      onResize(index, startWidth + (ev.clientX - startX));
    };
    const handleUp = () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
      document.body.classList.remove("ev-resizing");
      setDragging(false);
      onResizeEnd();
    };
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
  };

  return (
    <th className={TH_CLASSES[index]}>
      {COLUMNS[index].label}
      <span
        className={`ev-col-resizer${dragging ? " ev-col-resizer-active" : ""}`}
        onMouseDown={handleMouseDown}
        onDoubleClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onResetColumn(index);
        }}
        title="ドラッグで列幅を変更／ダブルクリックで既定幅に戻す"
      />
    </th>
  );
}

function ConversationCard({
  conv,
  widths,
  handlers,
}: {
  conv: EvaluatedConversation;
  widths: number[];
  handlers: ResizeHandlers;
}) {
  return (
    <details className="ev-conv" open>
      <summary className="ev-conv-header">
        <span className="ev-conv-id">Conversation:{conv.id}</span>
        <span className="ev-conv-date">{formatDate(conv.created_at)}</span>
      </summary>
      <div className="ev-table-wrap">
        <table className="ev-table">
          {/* 列幅は <col> 側に一本化する（.ev-table は table-layout: fixed, ADR-0087 決定2）。 */}
          <colgroup>
            {widths.map((w, i) => (
              <col key={COLUMNS[i].label} style={{ width: `${w}px` }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {widths.map((w, i) => (
                <ColumnHeader
                  key={COLUMNS[i].label}
                  index={i}
                  width={w}
                  handlers={handlers}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {conv.messages.map((msg) => (
              <MessageRow key={msg.id} msg={msg} />
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export default function EvaluatedMessagesPage() {
  const [data, setData] = useState<EvaluatedConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // リリースでの絞り込み（ADR-0099 §4）。"" はすべて。
  const [releaseFilter, setReleaseFilter] = useState("");

  /** 画面内に現れるリリース（初回日時の新しい順。詳細未登録のものは末尾）。 */
  const releases = useMemo(() => {
    const byId = new Map<string, Release | null>();
    for (const c of data) {
      for (const m of c.messages) {
        if (m.release_id && !byId.get(m.release_id)) byId.set(m.release_id, m.release);
      }
    }
    return [...byId.entries()].sort(
      ([, a], [, b]) => (b?.first_seen_at ?? "").localeCompare(a?.first_seen_at ?? ""),
    );
  }, [data]);

  const visible = useMemo(
    () =>
      releaseFilter
        ? data.filter((c) => c.messages.some((m) => m.release_id === releaseFilter))
        : data,
    [data, releaseFilter],
  );

  // 列幅は本ページで一元管理し、全 ConversationCard へ props として配る（ADR-0087 決定1）。
  // これにより、どのテーブルでドラッグしても画面内の全テーブルへ同時に反映される。
  const [widths, setWidths] = useState<number[]>(loadWidths);
  // 保存時に「その時点の最新の列幅」を参照するためのミラー（イベントリスナーは古い state を掴むため）。
  const widthsRef = useRef(widths);
  widthsRef.current = widths;

  useEffect(() => {
    getEvaluatedMessages()
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const handleResize = useCallback((index: number, width: number) => {
    // 最小幅でクランプする。最大幅の上限は設けない（横スクロールで閲覧する, ADR-0087 決定3）。
    setWidths((prev) => {
      const next = [...prev];
      next[index] = Math.max(COLUMNS[index].minWidth, Math.round(width));
      return next;
    });
  }, []);

  const handleResizeEnd = useCallback(() => {
    saveWidths(widthsRef.current);
  }, []);

  const handleResetColumn = useCallback((index: number) => {
    const next = [...widthsRef.current];
    next[index] = COLUMNS[index].defaultWidth;
    widthsRef.current = next;
    setWidths(next);
    saveWidths(next);
  }, []);

  const handleResetAll = useCallback(() => {
    const next = defaultWidths();
    setWidths(next);
    saveWidths(next);
  }, []);

  const handlers: ResizeHandlers = {
    onResize: handleResize,
    onResizeEnd: handleResizeEnd,
    onResetColumn: handleResetColumn,
  };

  return (
    <div className="ev-page">
      <h1 className="ev-title">評価済みメッセージ</h1>
      <div className="ev-toolbar">
        <label className="ev-filter">
          リリース
          <select value={releaseFilter} onChange={(e) => setReleaseFilter(e.target.value)}>
            <option value="">すべて</option>
            {releases.map(([id, r]) => (
              <option key={id} value={id}>
                {id.slice(0, 8)}
                {r?.first_seen_at ? `（${formatDate(r.first_seen_at)}〜）` : "（詳細未登録）"}
              </option>
            ))}
          </select>
        </label>
        <button className="ev-reset-btn" onClick={handleResetAll}>
          列幅をリセット
        </button>
      </div>
      {loading && <p className="ev-status">読み込み中...</p>}
      {error && <p className="ev-status ev-error">{error}</p>}
      {!loading && !error && data.length === 0 && (
        <p className="ev-status">データがありません</p>
      )}
      {!loading && !error && data.length > 0 && visible.length === 0 && (
        <p className="ev-status">このリリースの会話はありません</p>
      )}
      {visible.map((conv) => (
        <ConversationCard
          key={conv.id}
          conv={conv}
          widths={widths}
          handlers={handlers}
        />
      ))}
    </div>
  );
}
