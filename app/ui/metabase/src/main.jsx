// React browser entry point for the Metabase dashboard MCP App.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import MetabaseDashboardApp from "./App.jsx";
import "./style.css";

createRoot(document.querySelector("#root")).render(
    <StrictMode>
        <MetabaseDashboardApp />
    </StrictMode>,
);
