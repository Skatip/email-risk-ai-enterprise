from __future__ import annotations
from typing import Any, Callable, Dict
from app.gmail_service import fetch_full_thread, fetch_email_body, fetch_inbox_fast

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, handler: Callable[..., Any], *, risk: str = "read", requires_approval: bool = False):
        self.tools[name] = {"name": name, "description": description, "handler": handler, "risk": risk, "requires_approval": requires_approval}

    def manifest(self):
        return [{key: value for key, value in tool.items() if key != "handler"} for tool in self.tools.values()]

    def execute(self, name: str, arguments: Dict[str, Any], approved: bool = False):
        tool = self.tools.get(name)
        if not tool:
            raise KeyError(f"Unknown tool: {name}")
        if tool["requires_approval"] and not approved:
            return {"status": "approval_required", "tool": name, "arguments": arguments}
        return {"status": "ok", "tool": name, "result": tool["handler"](**arguments)}

registry = ToolRegistry()
registry.register("gmail.search", "Search the connected Gmail inbox.", lambda user_id="", query="", max_results=10: fetch_inbox_fast(query=query, max_results=max_results, user_id=user_id))
registry.register("gmail.read_message", "Read one Gmail message body.", lambda message_id, user_id="": fetch_email_body(message_id, user_id=user_id))
registry.register("gmail.read_thread", "Read a Gmail thread.", lambda thread_id, user_id="": fetch_full_thread(thread_id, user_id=user_id))
registry.register("calendar.check_availability", "Calendar adapter placeholder until Calendar OAuth is enabled.", lambda **kwargs: {"available": False, "reason": "Calendar integration is not enabled yet"})
