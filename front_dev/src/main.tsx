import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import App from "./App";
import AppStateless from "./AppStateless";
import AppEvaluatedMessages from "./AppEvaluatedMessages";

const path = window.location.pathname;

let root;
if (path === "/evaluated_messages") {
  document.body.classList.add("page-evaluated");
  root = <AppEvaluatedMessages />;
} else {
  root = <AppStateless />;
}

createRoot(document.getElementById("app")!).render(
  <StrictMode>{root}</StrictMode>,
);
