/**
 * 回答生成方式（ADR-0088 / ADR-0089 決定5）。
 *
 * - "pipeline": パイプライン方式。言い換え → タグ選定 → 情報源検索1回 → 回答生成の一本道（ADR-0043）。
 * - "agentic":  エージェント方式。検索 → 十分性評価 → クエリ再定式化で最大2周回し、
 *               見つからなければ逆質問を返す（ADR-0088）。
 *
 * 両方式のリクエスト・レスポンスの形式は完全に同一で、呼び出す web_backend のパスだけが変わる。
 */
export type AskMode = "pipeline" | "agentic";

/** web_backend 側のエンドポイント。agent_invitro の同名パスへ中継される。 */
export const ASK_MODE_PATH: Record<AskMode, string> = {
  pipeline: "/api/ask-pipeline",
  agentic: "/api/ask-agentic",
};

/** トグルの表示ラベル。 */
export const ASK_MODE_LABEL: Record<AskMode, string> = {
  pipeline: "パイプライン方式",
  agentic: "エージェント方式",
};

export const ASK_MODES: AskMode[] = ["pipeline", "agentic"];

/** 選択した方式の保存キー（ブラウザ単位。リロードしても選択を保つ）。 */
const STORAGE_KEY = "chat_ask_mode_v1";

export const DEFAULT_ASK_MODE: AskMode = "pipeline";

export function isAskMode(value: unknown): value is AskMode {
  return value === "pipeline" || value === "agentic";
}

/** 保存済みの方式を読み込む。未保存・不正値・localStorage 参照不可なら既定値を返す。 */
export function loadAskMode(): AskMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isAskMode(raw) ? raw : DEFAULT_ASK_MODE;
  } catch {
    return DEFAULT_ASK_MODE;
  }
}

export function saveAskMode(mode: AskMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // 保存できなくても動作は継続する（選択は当該タブ内でのみ有効になる）。
  }
}
