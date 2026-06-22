import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import App from "./App";
import AppStateless from "./AppStateless";

createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <AppStateless />
  </StrictMode>,
);
