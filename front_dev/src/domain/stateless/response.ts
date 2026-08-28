import { Message } from "./message";
import { Summary } from "./summary";
import { ConversationTag } from "./tag";

export interface Response {
  conversation_id: string;
  messages: Message[];
  summary: Summary;
  tags?: ConversationTag[];
}
