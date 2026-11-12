"""工具：可执行性判断，不执行写操作。返回 executable/reason_code/requires_human。"""
from __future__ import annotations

from typing import Dict, Optional

from app.business.order.service import can_execute
from app.tools.errors import ToolResult, error, success


async def run(ctx, order_id: str, action: str,
              params: Optional[Dict] = None) -> ToolResult:
    try:
        check = can_execute(order_id, action, params or {})
        return success(check)
    except Exception as e:  # noqa: BLE001
        return error("eligibility_check_failed", str(e))
