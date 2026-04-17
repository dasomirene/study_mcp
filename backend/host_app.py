import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langchain_mcp_adapters.client import MultiServerMCPClient

from backend import main_weather


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:9000/mcp")

app = FastAPI(title="Weather MCP Host App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = MultiServerMCPClient(
    {
        "weather": {
            "transport": "http",
            "url": MCP_URL,
        }
    }
)


async def get_mcp_tool(tool_name: str):
    cache = getattr(app.state, "mcp_tools", None)
    if cache is None:
        tools = await client.get_tools()
        cache = {getattr(tool, "name", ""): tool for tool in tools}
        app.state.mcp_tools = cache

    tool = cache.get(tool_name)
    if tool is None:
        raise RuntimeError(f"{tool_name} tool 을 찾을 수 없습니다.")
    return tool


def normalize_tool_result(fallback_location: str, result: Any) -> dict:
    if isinstance(result, dict):
        return result

    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"location": fallback_location, "weather": result, "temp": None}

    content = getattr(result, "content", None)
    if isinstance(content, list) and content:
        first = content[0]
        text = first.get("text") if isinstance(first, dict) else getattr(first, "text", None)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"location": fallback_location, "weather": text, "temp": None}

    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data

    return {"location": fallback_location, "weather": str(result), "temp": None}


@app.get("/")
async def root():
    return FileResponse(INDEX_FILE)


@app.get("/index.html")
async def index():
    return FileResponse(INDEX_FILE)


@app.get("/styles.css")
async def styles():
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")


@app.get("/app.js")
async def script():
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")


@app.get("/status")
async def status():
    return await main_weather.read_status()


@app.get("/weather")
async def weather(
    location: str = Query(..., min_length=1),
    selected_date: str | None = Query(None, alias="date"),
):
    try:
        tool = await get_mcp_tool("get_weather")
        raw_result = await tool.ainvoke({"location": location, "date": selected_date})
        return normalize_tool_result(location, raw_result)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"MCP get_weather 호출 실패: {error}")


@app.get("/astronomy")
async def astronomy(
    location: str = Query(..., min_length=1),
    selected_date: str | None = Query(None, alias="date"),
):
    try:
        tool = await get_mcp_tool("get_astronomy")
        raw_result = await tool.ainvoke({"location": location, "date": selected_date})
        return normalize_tool_result(location, raw_result)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"MCP get_astronomy 호출 실패: {error}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await main_weather.websocket_endpoint(websocket)
