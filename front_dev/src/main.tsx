import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import AppRoutes from "./routes";

// ルート定義は routes.tsx に集約。ここではマウントのみ行う。
createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <AppRoutes />
  </StrictMode>,
);
