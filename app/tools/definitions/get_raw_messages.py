"""工具：按 message_id 精确回捞原文（不参与语义检索）。"""
from __future__ import annotations

from typing import List

from app.memory.raw_store import get as raw_get
from app.tools.errors import ToolResult, empty, error, success


async def run(ctx, session_id: str, message_ids: List[str]) -> ToolResult:
    try:
        res = raw_get(message_ids)
        if not res.get("messages"):
            return empty({"messages": []})
        return success(res)
    except Exception as e:  # noqa: BLE001
        return error("get_raw_failed", str(e))
