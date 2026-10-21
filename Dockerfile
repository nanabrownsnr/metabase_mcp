# Metabase MCP — Twynity-native
# Pinned to Python 3.12: fastmcp 3.4.5 pulls jsonschema-path, which only
# publishes wheels up to 3.13. Do NOT build on 3.14 (Poetry/uv solve fails).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install uv (fast, reproducible) and use it to create the env + install deps.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (layer cache).
COPY pyproject.toml uv.lock* ./
RUN uv venv /app/.venv --python 3.12 \
    && uv pip install --python /app/.venv/bin/python -e .

# Copy application code.
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8000

EXPOSE 8000

# uvicorn serves the FastMCP ASGI app (app.main:app).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
