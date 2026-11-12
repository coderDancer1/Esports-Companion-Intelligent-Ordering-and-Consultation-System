"""投诉专家：评估情绪→转人工规则→创建工单；命中规则立即终止并打包上下文。"""
from __future__ import annotations

from typing import Dict

from app.orchestrator.experts.base import log_tool, result
from app.orchestrator.log_writer import write_handoff_log
from app.tools.definitions.assess_emotion import run as tool_assess
from app.tools.definitions.check_handoff_rules import run as tool_rules
from app.tools.definitions.create_handoff_ticket import run as tool_ticket


async def complaint_expert(ctx) -> Dict:
    emo = await tool_assess(ctx, message=ctx.message)
    log_tool(ctx, "assess_emotion", ctx.message[:20], emo.status)

    complaint_count = int(ctx.user_profile.get("complaint_count", 0) or 0)
    rules_res = await tool_rules(ctx, context={"message": ctx.message,
                                              "complaint_count": complaint_count})
    log_tool(ctx, "check_handoff_rules", "", rules_res.status)

    should_handoff = (rules_res.status == "success" and rules_res.data.get("should_handoff"))
    intensity = (emo.data or {}).get("intensity", 0.0) if emo.status == "success" else 0.0
    emo_labels = (emo.data or {}).get("labels", []) if emo.status == "success" else []
    emotion_desc = f"强度{intensity}，标签{'、'.join(emo_labels) if emo_labels else '未识别'}"

    if should_handoff or intensity >= 0.8:
        snapshot = {
            "detected_intent": "complaint",
            "emotion": emo.data if emo.status == "success" else {},
            "rule_id": (rules_res.data or {}).get("rule_id", ""),
            "recent": [m.get("content", "") for m in ctx.recent_messages[-3:]],
        }
        tk = await tool_ticket(ctx, type="complaint", summary=ctx.message[:100],
                               context_snapshot=snapshot)
        log_tool(ctx, "create_handoff_ticket", "", tk.status)
        if tk.status == "success":
            ticket_id = tk.data["ticket_id"]
            write_handoff_log(ctx.session_id, "complaint_rule_or_emotion", ticket_id, snapshot)
            return result("已为你创建工单，客服稍后联系你。", ticket_id=ticket_id, handoff_to_human=True,
                          facts={"情绪": emotion_desc, "处理方式": "已创建工单转人工"})
        return result("已记录你的投诉，客服稍后联系你。", handoff_to_human=True,
                      facts={"情绪": emotion_desc, "处理方式": "转人工"})

    return result("你的问题我已经记下了，如果仍需要处理，我可以帮你转人工客服。",
                  facts={"情绪": emotion_desc})
