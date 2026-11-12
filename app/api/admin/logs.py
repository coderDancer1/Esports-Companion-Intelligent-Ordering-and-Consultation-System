"""管理端：按 session_id 查路由日志与完整链路。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.admin import require_admin
from app.db.mysql import session_scope
from app.db.models import (CompressionLog, HandoffLog, RagLog, RouteLog, ToolLog)

router = APIRouter()


@router.get("/admin/logs/route")
async def route_logs(session_id: str, _admin=Depends(require_admin)):
    with session_scope() as db:
        rows = db.execute(select(RouteLog).where(RouteLog.session_id == session_id)
                          .order_by(RouteLog.turn_index)).scalars()
        return {"items": [_route_dict(r) for r in rows]}


@router.get("/admin/logs/session/{session_id}/trace")
async def trace(session_id: str, _admin=Depends(require_admin)):
    with session_scope() as db:
        route = [_route_dict(r) for r in db.execute(
            select(RouteLog).where(RouteLog.session_id == session_id)).scalars()]
        tool = [_tool_dict(r) for r in db.execute(
            select(ToolLog).where(ToolLog.session_id == session_id)).scalars()]
        rag = [_rag_dict(r) for r in db.execute(
            select(RagLog).where(RagLog.session_id == session_id)).scalars()]
        handoff = [_handoff_dict(r) for r in db.execute(
            select(HandoffLog).where(HandoffLog.session_id == session_id)).scalars()]
        compress = [_compress_dict(r) for r in db.execute(
            select(CompressionLog).where(CompressionLog.session_id == session_id)).scalars()]
    return {"session_id": session_id, "route_log": route, "tool_log": tool,
            "rag_log": rag, "handoff_log": handoff, "compression_log": compress}


def _route_dict(r):
    return {"turn_index": r.turn_index, "intent": r.intent, "confidence": r.confidence,
            "route_source": r.route_source, "reason": r.reason, "handoff_count": r.handoff_count,
            "created_at": r.created_at.isoformat() if r.created_at else None}


def _tool_dict(r):
    return {"turn_index": r.turn_index, "agent": r.agent, "tool_name": r.tool_name,
            "params_digest": r.params_digest, "status": r.status}


def _rag_dict(r):
    return {"channel": r.channel, "query": r.query, "top_k_scores": r.top_k_scores,
            "need_fallback": r.need_fallback}


def _handoff_dict(r):
    return {"trigger_rule": r.trigger_rule, "ticket_id": r.ticket_id,
            "context_snapshot": r.context_snapshot}


def _compress_dict(r):
    return {"token_before": r.token_before, "token_after": r.token_after,
            "summary_len": r.summary_len, "trigger_reason": r.trigger_reason}
