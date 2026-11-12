"""工具：确定性转人工规则校验（金额阈值/重复投诉/人身攻击）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.tools.errors import ToolResult, error, success

_ABUSE_WORDS = ["骂", "滚", "傻逼", "废物", "垃圾东西", "你妈"]
_AMOUNT_THRESHOLD_FEN = 50000  # 500 元


async def run(ctx, context: Optional[Dict[str, Any]] = None) -> ToolResult:
    try:
        context = context or {}
        # 1. 金额争议
        order = context.get("order") or {}
        if order.get("amount_fen", 0) >= _AMOUNT_THRESHOLD_FEN:
            return success({"should_handoff": True, "rule_id": "amount_threshold"})
        # 2. 重复投诉
        if (context.get("complaint_count", 0) or 0) >= 3:
            return success({"should_handoff": True, "rule_id": "repeat_complaint"})
        # 3. 人身攻击
        text = context.get("message", "")
        if any(w in text for w in _ABUSE_WORDS):
            return success({"should_handoff": True, "rule_id": "personal_abuse"})
        return success({"should_handoff": False, "rule_id": ""})
    except Exception as e:  # noqa: BLE001
        return error("handoff_rules_failed", str(e))
