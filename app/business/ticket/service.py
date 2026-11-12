"""工单服务：创建/查询/列表/更新状态。"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Ticket
from app.db.mysql import session_scope


def _new_id() -> str:
    return "tk_" + uuid.uuid4().hex[:10]


def _dict(t: Ticket) -> Dict[str, Any]:
    return {
        "ticket_id": t.id,
        "user_id": t.user_id,
        "session_id": t.session_id,
        "type": t.type,
        "status": t.status,
        "summary": t.summary,
        "context_snapshot": t.context_snapshot,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def create_ticket(user_id: str, type: str, summary: str,
                  session_id: str = "", context_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with session_scope() as db:
        ticket = Ticket(
            id=_new_id(), user_id=user_id, session_id=session_id, type=type,
            summary=summary, context_snapshot=context_snapshot or {}, status="pending",
        )
        db.add(ticket)
        db.flush()
        queue = db.execute(select(func.count()).select_from(Ticket).where(Ticket.status == "pending")).scalar() or 0
        return {"ticket_id": ticket.id, "queue_position": queue, "status": "pending"}


def get_ticket(ticket_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as db:
        t = db.get(Ticket, ticket_id)
        return _dict(t) if t else None


def list_tickets(user_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    with session_scope() as db:
        stmt = select(Ticket).order_by(Ticket.created_at.desc())
        if user_id:
            stmt = stmt.where(Ticket.user_id == user_id)
        if status:
            stmt = stmt.where(Ticket.status == status)
        return [_dict(t) for t in db.execute(stmt).scalars()]


def update_status(ticket_id: str, status: str) -> bool:
    with session_scope() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return False
        t.status = status
        return True
