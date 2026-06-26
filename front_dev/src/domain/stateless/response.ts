import { Message } from "./message";
import { Summary } from "./summary";

export interface Response {
  conversation_id: string;
  messages: Message[];
  summary: Summary;
}
