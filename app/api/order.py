"""订单 HTTP 接口：查详情/列表/取消/售后申请（内部走领域服务，不直接改状态）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.business.order.service import cancel_order, get_order_detail, query_orders
from app.business.ticket.service import create_ticket
from app.security.auth import AuthUser, get_auth_user

router = APIRouter()


class CancelRequest(BaseModel):
    reason: str = ""


class AfterSalesRequest(BaseModel):
    type: str = "refund"  # refund | change_playmate | reschedule
    detail: str = ""


def _ensure_owner(auth: AuthUser, order_id: str):
    order = get_order_detail(order_id)
    if not order or order.get("user_id") != auth.user_id:
        raise HTTPException(status_code=404, detail="order_not_found")
    return order


@router.get("/orders/{order_id}")
async def get_order(order_id: str, auth: AuthUser = Depends(get_auth_user)):
    return _ensure_owner(auth, order_id)


@router.get("/orders")
async def list_orders(status: Optional[str] = None, page: int = 1, size: int = 20,
                      auth: AuthUser = Depends(get_auth_user)):
    res = query_orders(user_id=auth.user_id, status=status)
    orders = res.get("orders", [])
    start = (page - 1) * size
    return {"total": len(orders), "items": orders[start:start + size]}


@router.post("/orders/{order_id}/cancel")
async def cancel(order_id: str, body: CancelRequest, auth: AuthUser = Depends(get_auth_user)):
    _ensure_owner(auth, order_id)
    res = cancel_order(order_id, body.reason, actor=auth.user_id)
    if res.get("status") == "success":
        return {"executable": True, "refund_amount": res.get("refund_amount"),
                "reason_code": res.get("reason_code", "OK")}
    if res.get("status") == "error":
        return {"executable": False, "refund_amount": None,
                "reason_code": res.get("reason_code", "not_executable"),
                "requires_human": res.get("requires_human", False)}
    return res


@router.post("/orders/{order_id}/after-sales")
async def after_sales(order_id: str, body: AfterSalesRequest, auth: AuthUser = Depends(get_auth_user)):
    _ensure_owner(auth, order_id)
    ticket = create_ticket(user_id=auth.user_id, type="after_sales", summary=body.detail or body.type,
                           context_snapshot={"order_id": order_id, "type": body.type})
    return {"ticket_id": ticket["ticket_id"], "status": ticket["status"]}
