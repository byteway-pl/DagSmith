import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import DagSmith from "./main";

// Standalone development entry point (`npm run dev`), not part of the UMD bundle.
createRoot(document.querySelector("#root") as HTMLDivElement).render(
  <StrictMode>
    <DagSmith />
  </StrictMode>,
);
