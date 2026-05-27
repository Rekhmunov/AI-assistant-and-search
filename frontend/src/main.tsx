import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/global.css";

declare const __BUILD_ID__: string;
document.documentElement.dataset.build = typeof __BUILD_ID__ !== "undefined" ? __BUILD_ID__ : "dev";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
