import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PhiShell } from "./PhiShell";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PhiShell />
  </StrictMode>,
);
