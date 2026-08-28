import { Message } from "./message";
import { Summary } from "./summary";
import { ConversationTag } from "./tag";

export interface Request {
  conversation_id?: string;
  text: string;
  messages: Message[];
  summary: Summary;
  tags?: ConversationTag[];
}
