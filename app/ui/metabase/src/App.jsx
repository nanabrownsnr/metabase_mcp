// Metabase dashboard MCP App: renders a dashboard as-is (grid of cards).
// The tool get_dashboard_tool returns structured_content with the dashboard's
// name, dashcards (each with card_id, name, visualization_type, size), and
// parameters/filters. This component lays them out on the 12-column grid.
import React, { useCallback, useState } from "react";
import {
    useApp,
    useDocumentTheme,
    useHostFonts,
    useHostStyleVariables,
} from "@modelcontextprotocol/ext-apps/react";

// Map Metabase viz types to a small label + emoji so the card is recognizable
// without rendering the actual chart (we only have metadata, not pixels).
const VIZ_LABELS = {
    table: ["Table", "▦"],
    bar: ["Bar chart", "▁▂▃▅"],
    line: ["Line chart", "⤳"],
    pie: ["Pie chart", "◔"],
    scatter: ["Scatter", "⁘"],
    area: ["Area chart", "⬒"],
    gauge: ["Gauge", "◕"],
    row: ["Row", "▬"],
    combo: ["Combo chart", "▆"],
    pivot: ["Pivot table", "⊞"],
    scalar: ["Scalar", "◆"],
    smartscalar: ["Smart scalar", "✦"],
    progress: ["Progress", "▰"],
    funnel: ["Funnel", "▼"],
    map: ["Map", "◍"],
    waterfall: ["Waterfall", "◫"],
    sankey: ["Sankey", "⇶"],
    "map-point": ["Map point", "◉"],
    "map-area": ["Map area", "▣"],
    "map-grid": ["Map grid", "▩"],
    "map-bubble": ["Map bubble", "◍"],
    "map-geography": ["Map geography", "⊕"],
    "map-routes": ["Map routes", "⤳"],
    "map-heat": ["Map heat", "▤"],
    "map-cluster": ["Map cluster", "⁘"],
};

function vizInfo(vizType) {
    const [label, glyph] = VIZ_LABELS[vizType] || [vizType || "Card", "▤"];
    return { label, glyph };
}

export default function MetabaseDashboardApp() {
    const [dashboard, setDashboard] = useState(null);
    const [hasResult, setHasResult] = useState(false);
    const [error, setError] = useState(null);

    const onAppCreated = useCallback((createdApp) => {
        // The host delivers the linked tool result (get_dashboard_tool) here.
        createdApp.ontoolresult = (result) => {
            const sc = result.structuredContent;
            if (!sc || sc.status === "error") {
                setError(sc?.error || "The dashboard tool returned an error.");
                setDashboard(null);
                setHasResult(true);
                return;
            }
            // Normalize dashcards: each has card_id, name, visualization_type,
            // and size [col_span, row_span].
            const dashcards = sc.dashcards || sc.cards || [];
            setDashboard({
                name: sc.name || "Dashboard",
                description: sc.description || "",
                dashcards: dashcards,
                parameters: sc.parameters || [],
            });
            setHasResult(true);
            setError(null);
        };
    }, []);

    const { app, isConnected, error: connError } = useApp({
        appInfo: { name: "metabase-dashboard-ui", version: "1.0.0" },
        capabilities: {},
        onAppCreated,
        autoResize: true,
    });

    useHostStyleVariables(app, app?.getHostContext());
    useHostFonts(app, app?.getHostContext());
    const theme = useDocumentTheme();

    // Render state.
    let body;
    if (connError) {
        body = <p className="error">Unable to connect to the MCP client: {connError.message}</p>;
    } else if (!isConnected) {
        body = <p className="status">Connecting to the MCP client…</p>;
    } else if (!hasResult) {
        body = <p className="status">Call the get_dashboard tool to render its result.</p>;
    } else if (error) {
        body = <p className="error">{error}</p>;
    } else if (dashboard) {
        body = (
            <div className="dashboard">
                <header className="dashboard-header">
                    <h1>{dashboard.name}</h1>
                    {dashboard.description && <p className="desc">{dashboard.description}</p>}
                </header>
                {dashboard.parameters.length > 0 && (
                    <div className="params">
                        {dashboard.parameters.map((p, i) => (
                            <span key={i} className="param-chip">
                                {p.name || p.label || `Param ${i + 1}`}
                            </span>
                        ))}
                    </div>
                )}
                <div className="grid">
                    {dashboard.dashcards.length === 0 && (
                        <p className="status">This dashboard has no cards yet.</p>
                    )}
                    {dashboard.dashcards.map((card, i) => {
                        const size = Array.isArray(card.size) ? card.size : [6, 4];
                        const { label, glyph } = vizInfo(card.visualization_type);
                        return (
                            <div
                                key={card.id || i}
                                className="card"
                                style={{
                                    gridColumn: `span ${Math.max(1, Math.min(12, size[0] || 6))}`,
                                    gridRow: `span ${Math.max(1, size[1] || 4)}`,
                                }}
                            >
                                <div className="card-glyph" aria-hidden="true">{glyph}</div>
                                <div className="card-name">{card.name || card.card_id || `Card ${i + 1}`}</div>
                                <div className="card-viz">{label}</div>
                            </div>
                        );
                    })}
                </div>
            </div>
        );
    }

    return (
        <main className="view" aria-live="polite" data-host-theme={theme}>
            {body}
        </main>
    );
}
