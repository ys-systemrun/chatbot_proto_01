import { useEffect, useState } from "react";
import { getEvaluatedMessages } from "../../api";
import type { EvaluatedConversation, EvaluatedMessage } from "../../domain/evaluated";

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

function MessageRow({ msg }: { msg: EvaluatedMessage }) {
  const roleLabel = msg.role === 1 ? "ユーザー" : "アシスタント";
  const evalLabel = msg.evaluation === 1 ? "👍" : msg.evaluation === 2 ? "👎" : "－";

  return (
    <tr className={`ev-row ev-role-${msg.role === 1 ? "user" : "assistant"}`}>
      <td className="ev-td ev-td-num">{msg.order}</td>
      <td className="ev-td">{roleLabel}</td>
      <td className="ev-td ev-td-center">{evalLabel}</td>
      <td className="ev-td ev-td-model">{msg.model ?? "－"}</td>
      <ExpandableCell text={msg.content} className="ev-td ev-td-content" />
      <ExpandableCell text={msg.input} className="ev-td ev-td-input" />
      <td className="ev-td ev-td-date">{formatDate(msg.created_at)}</td>
    </tr>
  );
}

function ConversationCard({ conv }: { conv: EvaluatedConversation }) {
  return (
    <details className="ev-conv" open>
      <summary className="ev-conv-header">
        <span className="ev-conv-id">Conversation:{conv.id}</span>
        <span className="ev-conv-date">{formatDate(conv.created_at)}</span>
      </summary>
      <div className="ev-table-wrap">
        <table className="ev-table">
          <thead>
            <tr>
              <th className="ev-th ev-td-num">#</th>
              <th className="ev-th">役割</th>
              <th className="ev-th ev-td-center">評価</th>
              <th className="ev-th ev-td-model">モデル</th>
              <th className="ev-th">本文</th>
              <th className="ev-th">LLM 入力</th>
              <th className="ev-th ev-td-date">登録日時</th>
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

  useEffect(() => {
    getEvaluatedMessages()
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="ev-page">
      <h1 className="ev-title">評価済みメッセージ</h1>
      {loading && <p className="ev-status">読み込み中...</p>}
      {error && <p className="ev-status ev-error">{error}</p>}
      {!loading && !error && data.length === 0 && (
        <p className="ev-status">データがありません</p>
      )}
      {data.map((conv) => (
        <ConversationCard key={conv.id} conv={conv} />
      ))}
    </div>
  );
}
