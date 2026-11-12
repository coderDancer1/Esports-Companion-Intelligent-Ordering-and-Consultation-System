"""工单 HTTP 接口：创建、查询、列表。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.business.ticket.service import create_ticket, get_ticket, list_tickets
from app.security.auth import AuthUser, get_auth_user

router = APIRouter()


class TicketCreate(BaseModel):
    session_id: str = ""
    user_id: Optional[str] = None
    type: str = "general"
    summary: str = ""
    context_snapshot: Optional[Dict[str, Any]] = None


@router.post("/tickets")
async def create(body: TicketCreate, auth: AuthUser = Depends(get_auth_user)):
    return create_ticket(user_id=auth.user_id, type=body.type, summary=body.summary,
                         session_id=body.session_id, context_snapshot=body.context_snapshot or {})


@router.get("/tickets/{ticket_id}")
async def get_one(ticket_id: str, auth: AuthUser = Depends(get_auth_user)):
    t = get_ticket(ticket_id)
    if not t or t.get("user_id") != auth.user_id:
        raise HTTPException(status_code=404, detail="ticket_not_found")
    return t


@router.get("/tickets")
async def list_all(status: Optional[str] = None, auth: AuthUser = Depends(get_auth_user)):
    return {"items": list_tickets(user_id=auth.user_id, status=status)}
