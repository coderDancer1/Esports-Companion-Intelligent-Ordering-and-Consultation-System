"""订单专家：查询订单、可执行性判断；写操作只判断+提参，不执行。"""
from __future__ import annotations

import re
from typing import Dict, Optional

from app.orchestrator.experts.base import log_tool, result
from app.tools.definitions.check_action_eligibility import run as tool_check
from app.tools.definitions.query_order import run as tool_query

_ACTION_MAP = {"退款": "refund", "退": "refund", "取消": "cancel", "改单": "change_playmate",
               "改派": "change_playmate", "换陪玩": "change_playmate", "改时间": "reschedule",
               "改期": "reschedule"}
_ACTION_CN = {"refund": "退款", "cancel": "取消", "change_playmate": "改派", "reschedule": "改期"}


def _extract_order_id(message: str) -> Optional[str]:
    m = re.search(r"\b(\d{8,20})\b", message)
    return m.group(1) if m else None


def _detect_action(message: str) -> Optional[str]:
    for word, action in _ACTION_MAP.items():
        if word in message:
            return action
    return None


def _has_any(message: str, *words: str) -> bool:
    return any(w in message for w in words)


def _format_order(o: Dict) -> str:
    return (f"订单 {o.get('order_id')}：状态【{o.get('status')}】，金额 {o.get('amount')} 元，"
            f"游戏 {o.get('game')}，托管状态 {o.get('escrow_status')}。")


async def order_expert(ctx) -> Dict:
    # 合规红线：未成年人禁止下单/充值/打赏
    if ctx.is_minor and _has_any(ctx.message, "下单", "充值", "打赏", "购买", "买陪玩", "付款"):
        return result("未成年用户不能下单、充值或打赏，请让监护人协助操作哦～")

    order_id = _extract_order_id(ctx.message) or ctx.structured_state.get("order_id")
    if not order_id:
        if _has_any(ctx.message, "下单", "充值", "打赏"):
            return result("下单需先在推荐中选择陪玩师；确认后由后端创建订单并托管资金，我不会直接操作。"
                          "可以先告诉我你想玩的游戏、段位和预算～")
        return result("请提供订单号，或告诉我你想查哪笔订单")

    r = await tool_query(ctx, order_id=order_id)
    log_tool(ctx, "query_order", order_id, r.status)
    if r.status == "empty":
        return result("没有查到这笔订单，请确认订单号")
    if r.status == "error":
        return result("暂时查不到订单信息，可以帮你转人工", detected_intent_change="human")

    orders = r.data.get("orders") or []
    order = orders[0]
    order_info = _format_order(order)
    action = _detect_action(ctx.message)
    if action:
        e = await tool_check(ctx, order_id=order_id, action=action, params={})
        log_tool(ctx, "check_action_eligibility", action, e.status)
        if e.status == "success":
            d = e.data or {}
            if d.get("requires_human"):
                return result("这笔订单的该操作需要人工核实，已为你转接",
                              detected_intent_change="human", facts={"订单": order_info})
            if d.get("executable"):
                refund = d.get("refund_amount")
                amt = f"，预计退回 {refund / 100:.2f} 元" if refund else ""
                return result(f"这笔订单可以{_ACTION_CN.get(action, action)}{amt}，确认后为你提交"
                              f"（由后端执行，我不会自动操作）",
                              facts={"订单": order_info,
                                     "操作判断": f"{_ACTION_CN.get(action, action)}可执行"})
        return result("暂时无法判断该操作，建议转人工", detected_intent_change="human",
                      facts={"订单": order_info})

    return result(_format_order(order), facts={"订单": order_info})
