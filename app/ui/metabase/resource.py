"""Register and serve the compiled UI resource for the Metabase dashboard viewer.

The only tool with a UI is get_dashboard_tool; the UI renders the dashboard
as-is (cards laid out on the grid, each showing its viz type + title). Change
``VIEW_URI`` with the matching value in the tool, and update ``VIEW_PATH`` only
if you change the frontend build output location.
"""

from pathlib import Path

from fastmcp.apps import AppConfig

VIEW_URI = "ui://metabase/index.html"
VIEW_PATH = Path(__file__).parent / "dist" / "index.html"


def load_view_html() -> str:
    """Load the compiled UI and explain how to create it when it is missing."""
    if not VIEW_PATH.is_file():
        raise RuntimeError(
            "The MCP App UI has not been built. Run `npm ci` and `npm run build` "
            "inside app/ui/metabase before starting the server."
        )
    return VIEW_PATH.read_text(encoding="utf-8")


def register_resource(mcp):
    # This ui:// resource is the HTML document an MCP Apps-capable client
    # renders when it sees the same URI in get_dashboard_tool's AppConfig.
    @mcp.resource(VIEW_URI, app=AppConfig())
    def metabase_dashboard_view():
        """Return the bundled MCP App UI for the Metabase dashboard viewer."""
        return load_view_html()
