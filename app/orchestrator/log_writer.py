"""日志写入：route/tool/rag/handoff/compression 各表（best-effort，失败不阻断）。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.db.mysql import session_scope
from app.db.models import HandoffLog, RagLog, RouteLog, ToolLog


def _safe(fn) -> None:
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass


def write_route_log(session_id: str, turn_index: int, decision, meta: Dict[str, str]) -> None:
    def do():
        with session_scope() as db:
            db.add(RouteLog(
                session_id=session_id, turn_index=turn_index,
                intent=decision.intent if decision else "",
                confidence=decision.confidence if decision else 0.0,
                route_source=decision.route_source if decision else "",
                reason=decision.reason if decision else "",
                handoff_count=int(meta.get("handoff_count", 0) or 0),
                pending_clarify_at_turn=bool(meta.get("pending_clarify")),
            ))
    _safe(do)


def write_tool_log(ctx, tool_name: str, params_digest: str, status: str) -> None:
    def do():
        with session_scope() as db:
            db.add(ToolLog(session_id=ctx.session_id, turn_index=ctx.turn_index,
                           agent=ctx.route_decision.get("intent", "") if ctx.route_decision else "",
                           tool_name=tool_name, params_digest=params_digest[:255], status=status))
    _safe(do)


def write_rag_log(session_id: str, channel: str, query: str, scores: List[float],
                  need_fallback: bool) -> None:
    def do():
        with session_scope() as db:
            db.add(RagLog(session_id=session_id, channel=channel, query=query,
                          top_k_scores=scores, need_fallback=need_fallback))
    _safe(do)


def write_handoff_log(session_id: str, trigger_rule: str, ticket_id: str,
                      context_snapshot: Dict[str, Any]) -> None:
    def do():
        with session_scope() as db:
            db.add(HandoffLog(session_id=session_id, trigger_rule=trigger_rule,
                              ticket_id=ticket_id, context_snapshot=context_snapshot))
    _safe(do)
