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

## Deploy (Docker)

The Dockerfile is **pinned to Python 3.12** — fastmcp 3.4.5 pulls
`jsonschema-path`, which has no wheels for Python 3.14, so a 3.14 build
(Poetry on Render's default image) fails to solve. Do not change the base image.

```bash
# Build + run locally (spins up a dev Mongo too)
docker compose up --build

# Or just the image
docker build -t metabase-mcp .
docker run --env-file .env -p 8000:8000 metabase-mcp
```

Health check: `GET /api/v1/health` → `{"status":"ok"}`.

### Render
A `render.yaml` is included (`runtime: docker`, health check on `/api/v1/health`).
Create the service from the repo, then add the env vars as **secrets** in the
dashboard: `MONGODB_URI`, `ENCRYPTION_KEY`, `ACCOUNT_SERVICE_URL`,
`ACCOUNT_SERVICE_JWKS_ENDPOINT`, `ACCOUNT_SERVICE_JWKS_CACHE_TTL`, `LICENSE_KEY`,
`LICENSE_SERVER_BASE_URL`, `LICENSE_SERVER_JWKS_ENDPOINT`,
`LICENSE_SERVER_ACTIVATION_ENDPOINT`, `USAGE_REPORT_ENDPOINT`, `PUBLIC_URL`,
`ALLOWED_ORIGINS`.
