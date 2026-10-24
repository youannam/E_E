import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import "./styles.css";


document.addEventListener("copy", (event) => { event.preventDefault(); });
document.addEventListener("cut", (event) => { event.preventDefault(); });
document.addEventListener("contextmenu", (event) => { event.preventDefault(); });
document.addEventListener("dragstart", (event) => { event.preventDefault(); });
document.addEventListener("keydown", (event) => {
  if (!(event.ctrlKey || event.metaKey)) return;
  const key = event.key.toLowerCase();
  if (["c", "x", "u", "s", "p"].includes(key)) event.preventDefault();
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
