"""订单领域服务：query / can_execute / execute。

每次迁移前做硬编码业务校验（取消时机/改派/超时/金额阈值），不提供万能改状态接口。
写操作由本层执行并写审计；Agent 只能调用 can_execute 做可执行性判断。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.business.order.repository import get_order, list_orders, write_transition
from app.business.order.state_machine import OrderSM, InvalidTransitionError
from app.db.mysql import session_scope
from app.db.models import Order

# 未开始服务、可无损退款的状态集合
_PRE_SERVICE = {"待支付", "已支付", "待接单"}


def _order_dict(o: Order) -> Dict[str, Any]:
    return {
        "order_id": o.id,
        "user_id": o.user_id,
        "playmate_id": o.playmate_id,
        "game": o.game,
        "status": o.status,
        "amount_fen": o.amount_fen,
        "amount": round(o.amount_fen / 100, 2),
        "escrow_status": o.escrow_status,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def query_orders(user_id: Optional[str] = None, order_id: Optional[str] = None,
                 status: Optional[str] = None) -> Dict[str, Any]:
    """查询订单；查无结果返回 status="empty"。"""
    with session_scope() as db:
        if order_id:
            o = get_order(db, order_id)
            if o is None:
                return {"status": "empty", "orders": []}
            if user_id and o.user_id != user_id:
                return {"status": "empty", "orders": []}
            return {"status": "success", "orders": [_order_dict(o)]}
        orders = list_orders(db, user_id=user_id, status=status)
        return {"status": "success", "orders": [_order_dict(o) for o in orders]}


def get_order_detail(order_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as db:
        o = get_order(db, order_id)
        return _order_dict(o) if o else None


def can_execute(order_id: str, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """可执行性判断：只读，不执行任何写操作。"""
    params = params or {}
    with session_scope() as db:
        o = get_order(db, order_id)
        if o is None:
            return {"executable": False, "reason_code": "order_not_found", "requires_human": False}
        status = o.status

        if action == "cancel":
            if status in _PRE_SERVICE:
                return {"executable": True, "reason_code": "OK", "requires_human": False,
                        "refund_amount": o.amount_fen}
            if status in {"服务中", "待验收"}:
                return {"executable": False, "reason_code": "in_progress_requires_human", "requires_human": True}
            if status in {"已完成", "已关闭", "售后中"}:
                return {"executable": False, "reason_code": "terminal_or_aftersale", "requires_human": False}
            return {"executable": False, "reason_code": "unknown_status", "requires_human": False}

        if action == "refund":
            if status in _PRE_SERVICE:
                return {"executable": True, "reason_code": "OK", "requires_human": False,
                        "refund_amount": o.amount_fen}
            # 已开始/已完成的服务退款需要人工核实
            return {"executable": False, "reason_code": "refund_requires_human", "requires_human": True}

        if action == "change_playmate":
            if status in {"已支付", "待接单"}:
                return {"executable": True, "reason_code": "OK", "requires_human": False}
            return {"executable": False, "reason_code": "change_not_allowed", "requires_human": True}

        if action == "reschedule":
            if status in _PRE_SERVICE:
                return {"executable": True, "reason_code": "OK", "requires_human": False}
            if status in {"服务中"}:
                return {"executable": False, "reason_code": "reschedule_requires_human", "requires_human": True}
            return {"executable": False, "reason_code": "reschedule_not_allowed", "requires_human": False}

        return {"executable": False, "reason_code": "unsupported_action", "requires_human": False}


def execute(action: str, order_id: str, actor: str = "user",
            params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """执行写操作（取消/退款/改派等），带状态机校验 + 资金操作 + 审计。"""
    params = params or {}
    with session_scope() as db:
        o = get_order(db, order_id)
        if o is None:
            return {"status": "empty", "reason_code": "order_not_found"}

        if action == "cancel":
            check = can_execute(order_id, "cancel", params)
            if not check.get("executable"):
                return {"status": "error", **check}
            from app.business.payment.escrow import refund as do_refund
            from_status = o.status
            o.status = "已关闭"
            o.escrow_status = "refunded"
            do_refund(db, order_id, o.amount_fen)
            write_transition(db, order_id, from_status, "已关闭", "cancel", actor, params.get("reason", ""))
            return {"status": "success", "executable": True, "refund_amount": o.amount_fen,
                    "reason_code": "OK", "order": _order_dict(o)}

        # 通用状态机迁移（pay/accept/deliver/confirm/raise_after_sales/resolve）
        if action in {t.name for t in OrderSM.transitions}:
            from_status = o.status
            try:
                new_status = OrderSM.apply(o, action)
            except InvalidTransitionError as e:
                return {"status": "error", "reason_code": "invalid_transition", "error_message": str(e)}
            write_transition(db, order_id, from_status, new_status, action, actor, "")
            return {"status": "success", "order": _order_dict(o)}

        return {"status": "error", "reason_code": "unsupported_action"}


def cancel_order(order_id: str, reason: str, actor: str = "user") -> Dict[str, Any]:
    """取消订单（HTTP 接口入口）。"""
    return execute("cancel", order_id, actor=actor, params={"reason": reason})
