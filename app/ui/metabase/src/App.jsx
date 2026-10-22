// Metabase dashboard MCP App: renders the LIVE dashboard via iframe when it's
// publicly shared (Metabase's /public/dashboard route is iframe-able), and
// falls back to a structural grid (card positions/sizes/viz types) when the
// dashboard isn't public.
import React, { useCallback, useState } from "react";
import {
    useApp,
    useDocumentTheme,
    useHostFonts,
    useHostStyleVariables,
} from "@modelcontextprotocol/ext-apps/react";

const VIZ_LABELS = {
    table: ["Table", "▦"], bar: ["Bar chart", "▁▂▃▅"], line: ["Line chart", "⤳"],
    pie: ["Pie chart", "◔"], scatter: ["Scatter", "⁘"], area: ["Area chart", "⬒"],
    gauge: ["Gauge", "◕"], row: ["Row", "▬"], combo: ["Combo chart", "▆"],
    pivot: ["Pivot table", "⊞"], scalar: ["Scalar", "◆"], smartscalar: ["Smart scalar", "✦"],
    progress: ["Progress", "▰"], funnel: ["Funnel", "▼"], map: ["Map", "◍"],
    waterfall: ["Waterfall", "◫"], sankey: ["Sankey", "⇶"],
};

function vizInfo(vizType) {
    const [label, glyph] = VIZ_LABELS[vizType] || [vizType || "Card", "▤"];
    return { label, glyph };
}

export default function MetabaseDashboardApp() {
    const [dashboard, setDashboard] = useState(null);
    const [hasResult, setHasResult] = useState(false);
    const [error, setError] = useState(null);
    const [iframeFailed, setIframeFailed] = useState(false);

    const onAppCreated = useCallback((createdApp) => {
        createdApp.ontoolresult = (result) => {
            const sc = result.structuredContent;
            if (!sc || sc.status === "error") {
                setError(sc?.error || "The dashboard tool returned an error.");
                setDashboard(null);
                setHasResult(true);
                return;
            }
            setDashboard({
                name: sc.name || sc.dashboard?.name || "Dashboard",
                description: sc.description || sc.dashboard?.description || "",
                dashcards: sc.dashcards || sc.dashboard?.dashcards || [],
                parameters: sc.parameters || sc.dashboard?.parameters || [],
                uuid: sc.uuid || sc.dashboard?.uuid || null,
                public: sc.public,
                embed_url: sc.embed_url,
            });
            setIframeFailed(false);
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

    // Live embed: iframe the real Metabase dashboard. We can't reliably detect
    // an iframe load failure cross-origin, so we offer a "show layout instead"
    // toggle that the user can tap if the embed doesn't load (e.g. not public).
    if (dashboard && dashboard.embed_url && !iframeFailed) {
        return (
            <main className="embed-view" data-host-theme={theme} aria-label={dashboard.name}>
                <header className="embed-header">
                    <h1>{dashboard.name}</h1>
                    {dashboard.description && <p className="desc">{dashboard.description}</p>}
                    <button className="layout-toggle" onClick={() => setIframeFailed(true)}>
                        Show layout instead
                    </button>
                </header>
                <iframe
                    className="live-dashboard"
                    src={dashboard.embed_url}
                    title={dashboard.name}
                    loading="lazy"
                    referrerPolicy="no-referrer"
                    sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
                />
            </main>
        );
    }

    // Fallback (or no embed_url): structural grid of cards.
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
                    {dashboard.embed_url && !dashboard.public && (
                        <p className="note">
                            This dashboard isn't publicly shared, so the live embed is unavailable.
                            Share it publicly in Metabase to see it here.
                        </p>
                    )}
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
