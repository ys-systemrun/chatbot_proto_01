import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import QaListPage from "./feature/qa_admin/QaListPage";
import QaFormPage from "./feature/qa_admin/QaFormPage";
import TagTreePage from "./feature/tag_admin/TagTreePage";

// 管理画面（/admin 配下）のルーティング定義（ADR-0015 / IMPL-202608060837 T15）。
// 既存3画面（App / AppStateless / AppEvaluatedMessages）とは独立し、/admin のみ react-router-dom を用いる。
export default function AppAdmin() {
  return (
    <BrowserRouter>
      <div className="admin-shell">
        <nav className="admin-nav">
          <span className="admin-nav-brand">QA・タグ管理</span>
          <NavLink to="/admin/qa" className="admin-nav-link">
            QA
          </NavLink>
          <NavLink to="/admin/tags" className="admin-nav-link">
            タグ
          </NavLink>
        </nav>
        <Routes>
          <Route path="/admin/qa" element={<QaListPage />} />
          <Route path="/admin/qa/new" element={<QaFormPage mode="create" />} />
          <Route path="/admin/qa/:id" element={<QaFormPage mode="edit" />} />
          <Route path="/admin/tags" element={<TagTreePage />} />
          <Route path="/admin" element={<Navigate to="/admin/qa" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
