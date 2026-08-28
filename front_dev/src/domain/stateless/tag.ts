// 会話タグ（IMPL-202608261345 T1 / ADR-0056）。
// score・missed_turns は agent_invitro（backend）が算出する値であり、
// クライアントは意味を解釈せずそのまま次回リクエストへ渡す（不透明な値）。
export interface ConversationTag {
  id: number;
  name: string;
  score: number;
  missed_turns: number;
}
