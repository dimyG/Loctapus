/**
 * Browser entry point: mounts the React tree on the page's #root element.
 * StrictMode double-invokes render and effects in development so accidental
 * side effects surface early; it has no effect in production builds.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./app/App";
import "./theme/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
