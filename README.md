# Metabase MCP (Twynity-native)

A Twynity MCP server for Metabase. Each Twynity user connects **their own**
Metabase instance with a **base URL + API key**, stored encrypted in MongoDB,
scoped to `(user_id, persona_id)`.

## Tools
- `check_metabase_connection` — verify the API key works
- `metabase_search` — search cards/dashboards/collections
- `list_databases_tool` — list connected databases
- `list_dashboards_tool` — list dashboards (optionally by collection)
- `get_dashboard_tool` — fetch a dashboard + its cards
- `run_card_tool` — run a saved question and return rows

## Auth model
- FastMCP `JWTVerifier` protects the MCP transport (Twynity bearer + Persona-Id).
- Custom routes (`/api/v1/*`) verify the JWT manually against account-service JWKS.
- Metabase API key is stored encrypted (Fernet) per user/persona; tools read it
  from the store — never from tool arguments.

## Run
    uv sync
    uv run python -m uvicorn src.metabase_mcp.main:app --port 8000

## Configure (per user)
    POST /api/v1/configuration
    {"base_url": "https://metabase.example.com", "api_key": "***"}
