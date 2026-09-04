import { useState } from "react";
import { downloadExport } from "../../api";

// 全データエクスポート画面（IMPL-202608241600 T21、5.6 節）。
// SQL / CSV をラジオボタンで選び、「エクスポート」で ZIP をダウンロードする。処理中は
// ボタンを無効化して多重クリックを防ぎ、成功・失敗をページ内にメッセージ表示する。

type Format = "sql" | "csv";

export default function ExportPage() {
  const [format, setFormat] = useState<Format>("sql");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onExport() {
    setLoading(true);
    setMessage(null);
    setError(null);
    try {
      await downloadExport(format);
      setMessage(`${format.toUpperCase()} 形式でエクスポートしました。`);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <h1 className="admin-title">全データエクスポート</h1>
      </div>

      <p className="admin-muted">
        chatbot データベース（7テーブル）と conversation データベース（6テーブル）の全13テーブルの
        全データを ZIP でダウンロードします。CSV は表計算ソフト用（埋め込みベクトルは除外）、SQL は空の
        PostgreSQL へ再投入できる形式です。
      </p>

      <fieldset className="admin-export-formats">
        <legend>形式</legend>
        <label className="admin-export-radio">
          <input
            type="radio"
            name="export-format"
            value="sql"
            checked={format === "sql"}
            onChange={() => setFormat("sql")}
            disabled={loading}
          />
          SQL（psql -f で再投入可能）
        </label>
        <label className="admin-export-radio">
          <input
            type="radio"
            name="export-format"
            value="csv"
            checked={format === "csv"}
            onChange={() => setFormat("csv")}
            disabled={loading}
          />
          CSV（テーブルごと・Excel 等で閲覧）
        </label>
      </fieldset>

      <button
        className="admin-btn admin-btn-primary"
        onClick={onExport}
        disabled={loading}
      >
        {loading ? "エクスポート中..." : "エクスポート"}
      </button>

      {message && <p className="admin-status">{message}</p>}
      {error && <p className="admin-status admin-error">{error}</p>}
    </div>
  );
}
