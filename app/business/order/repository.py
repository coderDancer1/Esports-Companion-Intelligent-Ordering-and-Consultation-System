"""订单数据访问：查询、按状态过滤、迁移审计写入。"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Order, OrderTransition, now


def get_order(db: Session, order_id: str) -> Optional[Order]:
    return db.get(Order, order_id)


def list_orders(db: Session, user_id: Optional[str] = None, status: Optional[str] = None,
                limit: int = 50) -> List[Order]:
    stmt = select(Order)
    if user_id:
        stmt = stmt.where(Order.user_id == user_id)
    if status:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars())


def write_transition(db: Session, order_id: str, from_status: str, to_status: str,
                     action: str, actor: str, reason: str = "") -> None:
    db.add(OrderTransition(
        order_id=order_id, from_status=from_status, to_status=to_status,
        action=action, actor=actor, reason=reason, created_at=now(),
    ))
