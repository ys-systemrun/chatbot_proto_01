import { Message } from "./message";
import { Summary } from "./summary";

export interface Response {
  messages: Message[];
  summary: Summary;
}
