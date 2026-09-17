import { Message } from "./message";
import { Summary } from "./summary";

export interface Request {
  conversation_id?: string;
  text: string;
  messages: Message[];
  summary: Summary;
}
