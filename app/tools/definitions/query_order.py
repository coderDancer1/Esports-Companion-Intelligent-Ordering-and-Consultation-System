"""工具：查询订单；user_id 从 ctx 取，不接受模型传入。empty/error 严格区分。"""
from __future__ import annotations

from typing import Optional

from app.business.order.service import query_orders
from app.tools.errors import ToolResult, empty, error, success


async def run(ctx, order_id: Optional[str] = None) -> ToolResult:
    try:
        res = query_orders(user_id=ctx.user_id, order_id=order_id)
        if res.get("status") == "empty":
            return empty({"orders": []})
        return success({"orders": res["orders"]})
    except Exception as e:  # noqa: BLE001
        return error("query_order_failed", str(e))
