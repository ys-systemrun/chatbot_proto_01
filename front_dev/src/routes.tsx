import { useEffect } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  NavLink,
  Outlet,
} from "react-router-dom";
import { StateContainer } from "./feature/stateless/StateContainer";
import EvaluatedMessagesPage from "./feature/evaluated_messages/EvaluatedMessagesPage";
import QaListPage from "./feature/qa_admin/QaListPage";
import QaFormPage from "./feature/qa_admin/QaFormPage";
import QuestionAlteredListPage from "./feature/question_altered/QuestionAlteredListPage";
import QuestionAlteredFormPage from "./feature/question_altered/QuestionAlteredFormPage";
import TagTreePage from "./feature/tag_admin/TagTreePage";
import ExportPage from "./feature/export/ExportPage";
import VerificationListPage from "./feature/verification/VerificationListPage";
import VerificationFormPage from "./feature/verification/VerificationFormPage";
import VerificationDetailPage from "./feature/verification/VerificationDetailPage";

// front_dev/src のルート定義を集約する唯一のファイル（旧: main.tsx の window.location.pathname 分岐 +
// AppAdmin / AppStateless / AppEvaluatedMessages の 3 エントリを本ファイルへ統合）。
// AWS 単一プロセス構成では web_backend 側の SPA フォールバック（catch-all）が index.html を返すため、
// URL 直接入力・リロードでも本 Router がその path から起動する（ADR-0015 / ADR-0042）。

/**
 * 画面グループごとに <body> のクラスを付け替える（CSS の body.page-* セレクタ用）。
 * アンマウント時に取り除き、SPA 内遷移でクラスが残留しないようにする。
 */
function useBodyClass(className: string): void {
  useEffect(() => {
    document.body.classList.add(className);
    return () => document.body.classList.remove(className);
  }, [className]);
}

/**
 * 全画面共通のグローバルナビ。チャット / 管理 / 評価 の 3 画面グループを相互に行き来する。
 * 各画面グループ内のナビ（例: 管理の QA/タグ/エクスポート）は各レイアウト側に残す。
 */
function GlobalNav() {
  return (
    <nav className="global-nav">
      <NavLink to="/" end className="global-nav-link">
        チャット
      </NavLink>
      <NavLink to="/admin" className="global-nav-link">
        管理
      </NavLink>
      <NavLink to="/evaluated_messages" className="global-nav-link">
        評価
      </NavLink>
    </nav>
  );
}

/** 全ルート共通のルートレイアウト。グローバルナビを常時表示し、各画面を <Outlet /> に描画する。 */
function RootLayout() {
  return (
    <>
      <GlobalNav />
      <Outlet />
    </>
  );
}

/** 評価済みメッセージ画面（旧 AppEvaluatedMessages）。body.page-evaluated を付与する。 */
function EvaluatedLayout() {
  useBodyClass("page-evaluated");
  return <EvaluatedMessagesPage />;
}

/**
 * 管理画面レイアウト（旧 AppAdmin）。body.page-admin と共通ナビを付与し、
 * 子ルート（QA / タグ）を <Outlet /> に描画する。
 */
function AdminLayout() {
  useBodyClass("page-admin");
  return (
    <div className="admin-shell">
      <nav className="admin-nav">
        <span className="admin-nav-brand">QA・タグ管理</span>
        <NavLink to="/admin/qa" className="admin-nav-link">
          QA
        </NavLink>
        <NavLink to="/admin/hiroba_question_altered" className="admin-nav-link">
          言い換え
        </NavLink>
        <NavLink to="/admin/tags" className="admin-nav-link">
          タグ
        </NavLink>
        <NavLink to="/admin/verification" className="admin-nav-link">
          検証
        </NavLink>
        <NavLink to="/admin/export" className="admin-nav-link">
          エクスポート
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}

export default function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        {/* 全ルートをグローバルナビ付きのルートレイアウトで包む */}
        <Route element={<RootLayout />}>
          {/* チャット（stateless）: 旧 AppStateless。デフォルト画面 */}
          <Route path="/" element={<StateContainer />} />

          {/* 評価済みメッセージ一覧: 旧 AppEvaluatedMessages */}
          <Route path="/evaluated_messages" element={<EvaluatedLayout />} />

          {/* 管理画面（QA・タグ）: 旧 AppAdmin の入れ子ルート */}
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="/admin/qa" replace />} />
            <Route path="qa" element={<QaListPage />} />
            <Route path="qa/new" element={<QaFormPage mode="create" />} />
            <Route path="qa/:id" element={<QaFormPage mode="edit" />} />
            <Route
              path="hiroba_question_altered"
              element={<QuestionAlteredListPage />}
            />
            <Route
              path="hiroba_question_altered/new"
              element={<QuestionAlteredFormPage mode="create" />}
            />
            <Route
              path="hiroba_question_altered/:id"
              element={<QuestionAlteredFormPage mode="edit" />}
            />
            <Route path="tags" element={<TagTreePage />} />
            <Route path="verification" element={<VerificationListPage />} />
            <Route
              path="verification/new"
              element={<VerificationFormPage mode="create" />}
            />
            <Route
              path="verification/:id"
              element={<VerificationDetailPage />}
            />
            <Route
              path="verification/:id/edit"
              element={<VerificationFormPage mode="edit" />}
            />
            <Route path="export" element={<ExportPage />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
