import { Message } from "./message";
import { Summary } from "./summary";

export interface Request {
  text: string;
  messages: Message[];
  summary: Summary;
}
