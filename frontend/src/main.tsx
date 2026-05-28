import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { initUserSettings } from "./lib/userSettings";
import "./index.css";

initUserSettings();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
