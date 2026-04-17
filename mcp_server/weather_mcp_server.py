import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from backend.main_weather import get_astronomy as fetch_astronomy
from backend.main_weather import get_weather as fetch_weather


MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "9000"))
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http")

mcp = FastMCP("weather", host=MCP_HOST, port=MCP_PORT)


@mcp.tool()
def get_weather(location: str, date: Optional[str] = None) -> dict:
    """Get weather information for a location and optional YYYY-MM-DD date."""
    return fetch_weather(location, date)


@mcp.tool()
def get_astronomy(location: str, date: Optional[str] = None) -> dict:
    """Get sun and moon information for a location and optional YYYY-MM-DD date."""
    return fetch_astronomy(location, date)


if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
