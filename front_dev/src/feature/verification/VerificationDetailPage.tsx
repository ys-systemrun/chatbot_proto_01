import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getVerificationQuestion,
  runVerification,
  saveVerificationEvaluation,
} from "../../api";
import type {
  VerificationQuestionDetail,
  VerificationRun,
} from "../../domain/admin/verification";

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "－";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** 1実行分の表示 + 評価入力。評価保存後は onSaved で親の再取得を促す。 */
function RunCard({
  run,
  onSaved,
}: {
  run: VerificationRun;
  onSaved: () => void;
}) {
  const [evaluation, setEvaluation] = useState<0 | 1 | null>(run.evaluation);
  const [comment, setComment] = useState(run.evaluation_comment ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function onSave() {
    if (evaluation == null) {
      setError("「適切」または「不適切」を選択してください。");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await saveVerificationEvaluation(run.id, {
        evaluation,
        comment: comment || null,
      });
      setMessage("評価を保存しました。");
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <details className="admin-run-card" open>
      <summary>
        {fmtDateTime(run.executed_at)} ／{" "}
        <span className={run.status === "error" ? "admin-error" : undefined}>
          {run.status === "error" ? "エラー" : "成功"}
        </span>
        {run.evaluation === 1 && "（適切）"}
        {run.evaluation === 0 && "（不適切）"}
      </summary>

      {run.status === "error" && run.error_message && (
        <p className="admin-status admin-error">{run.error_message}</p>
      )}

      <p className="admin-hint">
        既存タグ:{" "}
        {run.existing_tags_snapshot.length
          ? run.existing_tags_snapshot.join(", ")
          : "－"}
        {/* 追加（IMPL-202608261510 T8） */}
      </p>
      <p className="admin-hint">
        max_tags={run.max_tags ?? "－"} / confidence≥
        {run.confidence_threshold ?? "－"} / top_k={run.top_k ?? "－"} / min_score≥
        {run.min_score ?? "－"} / tag_selector={run.tag_selector_latency_ms ?? "－"}ms
        / knowledge={run.knowledge_mcp_latency_ms ?? "－"}ms
      </p>

      <h4>新規タグ</h4>
      <table className="admin-table">
        <thead>
          <tr>
            <th>順位</th>
            <th>タグ</th>
            <th>スコア</th>
            <th>パス</th>
          </tr>
        </thead>
        <tbody>
          {run.tags.map((t) => (
            <tr key={`${run.id}-tag-${t.rank_no}`}>
              <td>{t.rank_no}</td>
              <td>{t.tag_name}</td>
              <td>{t.score != null ? t.score.toFixed(4) : "－"}</td>
              <td>{t.path.length ? t.path.join(" › ") : "－"}</td>
            </tr>
          ))}
          {run.tags.length === 0 && (
            <tr>
              <td colSpan={4} className="admin-muted">
                選択タグなし
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h4>情報源</h4>
      {run.sources.map((s) => (
        <div key={`${run.id}-src-${s.rank_no}`} className="admin-source">
          <div className="admin-source-head">
            #{s.rank_no} {s.title ?? s.source_id ?? "(無題)"}{" "}
            <span className="admin-hint">
              [{s.source_type ?? "?"}]{" "}
              {s.score != null ? `score=${s.score.toFixed(4)}` : ""}
            </span>
          </div>
          {s.content && (
            <pre className="admin-source-content">{s.content}</pre>
          )}
        </div>
      ))}
      {run.sources.length === 0 && (
        <p className="admin-muted">情報源なし</p>
      )}

      <div className="admin-eval">
        <span className="admin-label">評価</span>
        <label className="admin-export-radio">
          <input
            type="radio"
            name={`eval-${run.id}`}
            checked={evaluation === 1}
            onChange={() => setEvaluation(1)}
            disabled={saving}
          />
          適切
        </label>
        <label className="admin-export-radio">
          <input
            type="radio"
            name={`eval-${run.id}`}
            checked={evaluation === 0}
            onChange={() => setEvaluation(0)}
            disabled={saving}
          />
          不適切
        </label>
        <textarea
          className="admin-textarea"
          placeholder="コメント（任意）"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={2}
          disabled={saving}
        />
        <button
          className="admin-btn admin-btn-primary"
          onClick={onSave}
          disabled={saving}
        >
          {saving ? "保存中..." : "評価を保存"}
        </button>
        {message && <span className="admin-status">{message}</span>}
        {error && <span className="admin-status admin-error">{error}</span>}
      </div>
    </details>
  );
}

export default function VerificationDetailPage() {
  const { id } = useParams();
  const [detail, setDetail] = useState<VerificationQuestionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const reload = useCallback(() => {
    if (!id) return;
    setLoading(true);
    getVerificationQuestion(Number(id))
      .then(setDetail)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function onRun() {
    if (!id) return;
    setRunning(true);
    setError(null);
    try {
      await runVerification(Number(id));
      reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  if (loading && !detail) return <p className="admin-status">読み込み中...</p>;
  if (!detail) {
    return (
      <div className="admin-page">
        {error && <p className="admin-status admin-error">{error}</p>}
        <Link className="admin-link" to="/admin/verification">
          ← 一覧へ戻る
        </Link>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">検証質問 詳細</h1>
        <Link className="admin-link" to="/admin/verification">
          ← 一覧へ戻る
        </Link>
      </div>

      {error && <p className="admin-status admin-error">{error}</p>}

      <div className="admin-form">
        <div className="admin-field">
          <span className="admin-label">質問文</span>
          <p>{detail.question_text}</p>
        </div>
        <div className="admin-field">
          <span className="admin-label">メモ</span>
          <p>{detail.memo || "－"}</p>
        </div>
        <div className="admin-field">
          <span className="admin-label">既存タグ</span>
          <p className="admin-hint">
            {detail.existing_tags.length ? detail.existing_tags.join(", ") : "－"}
          </p>
        </div>
        <div className="admin-form-actions">
          <Link
            className="admin-btn"
            to={`/admin/verification/${detail.id}/edit`}
          >
            編集
          </Link>
          <button
            className="admin-btn admin-btn-primary"
            onClick={onRun}
            disabled={running}
          >
            {running ? "実行中..." : "再実行"}
          </button>
        </div>
      </div>

      <h2 className="admin-title">実行履歴（{detail.runs.length} 件）</h2>
      {detail.runs.length === 0 && (
        <p className="admin-muted">まだ実行されていません。「再実行」で検証を開始します。</p>
      )}
      {detail.runs.map((run) => (
        <RunCard key={run.id} run={run} onSaved={reload} />
      ))}
    </div>
  );
}
