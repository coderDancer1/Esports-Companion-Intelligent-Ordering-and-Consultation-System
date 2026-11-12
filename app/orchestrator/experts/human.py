"""转人工专家：创建工单、记录 handoff_log、返回排队信息。"""
from __future__ import annotations

from typing import Dict

from app.orchestrator.experts.base import log_tool, result
from app.orchestrator.log_writer import write_handoff_log
from app.tools.definitions.create_handoff_ticket import run as tool_ticket


async def human_expert(ctx, reason: str = "") -> Dict:
    snapshot = {"reason": reason, "intent": ctx.route_decision.get("intent", "") if ctx.route_decision else ""}
    tk = await tool_ticket(ctx, type="general", summary=ctx.message[:100], context_snapshot=snapshot)
    log_tool(ctx, "create_handoff_ticket", "", tk.status)
    if tk.status == "success":
        ticket_id = tk.data["ticket_id"]
        queue = tk.data.get("queue_position", "-")
        write_handoff_log(ctx.session_id, reason or "manual", ticket_id, snapshot)
        return result(f"已为你创建工单（当前排队第 {queue} 位），客服稍后联系你。",
                      ticket_id=ticket_id, handoff_to_human=True,
                      facts={"排队位置": queue})
    return result("已记录你的需求，客服稍后联系你。", handoff_to_human=True)
