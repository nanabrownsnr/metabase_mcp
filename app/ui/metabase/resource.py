"""UI resource for Replicate MCP integration."""

import os
from pathlib import Path

from fastmcp.apps import register_resource

VIEW_URI = "ui://metabase/index.html"
RESOURCE_DIR = Path(__file__).parent / "metabase"


def register_resource(mcp):
    """Register the Replicate UI resource paths."""
    
    # Register index.html for the root view
    index_path = RESOURCE_DIR / "index.html"
    if index_path.exists():
        mcp.add_resource(VIEW_URI, index_path.read_text(encoding="utf-8"))
        
    # Register other static UI files if they exist
    for file_path in RESOURCE_DIR.glob("*"):
        if file_path.is_file() and file_path.name != "index.html":
            resource_uri = f"ui://metabase/{file_path.name}"
            mcp.add_resource(resource_uri, file_path.read_text(encoding="utf-8"))