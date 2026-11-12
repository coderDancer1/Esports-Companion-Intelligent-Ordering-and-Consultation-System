"""工具：创建转人工工单，返回 ticket_id。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.business.ticket.service import create_ticket
from app.tools.errors import ToolResult, error, success


async def run(ctx, type: str = "general", summary: str = "",
              context_snapshot: Optional[Dict[str, Any]] = None) -> ToolResult:
    try:
        res = create_ticket(user_id=ctx.user_id, type=type, summary=summary,
                            session_id=ctx.session_id, context_snapshot=context_snapshot or {})
        return success(res)
    except Exception as e:  # noqa: BLE001
        return error("create_ticket_failed", str(e))
