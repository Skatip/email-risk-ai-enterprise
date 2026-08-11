from fastapi import APIRouter, Body, HTTPException
from typing import Any, Dict
from app.mcp.tool_registry import registry

router = APIRouter(prefix="/mcp", tags=["MCP Tools"])

@router.get("/tools")
def tools():
    return registry.manifest()

@router.post("/execute")
def execute(payload: Dict[str, Any] = Body(...)):
    try:
        return registry.execute(payload.get("name", ""), payload.get("arguments") or {}, bool(payload.get("approved", False)))
    except Exception as exc:
        raise HTTPException(400, str(exc))
