"""数据飞轮：把线上弱信号归集成候选评测样例。

信号源（四类）：
  1. 显式负反馈  Feedback(rating=-1)          —— 意图误判 / 答复未 grounded / 知识缺失
  2. RAG 未命中   RagLog(need_fallback=True)   —— 知识库缺口（提示补文档）
  3. 工具异常     ToolLog(status in error/bad_input) —— 工具参数/实现问题
  4. 转人工       HandoffLog                    —— 自助链路没能解决的高优先级 badcase

原则：只「采集 + 归集 + 人工审核」，不做在线自动重训（小样本会漂移、无 canary）。
产物是待人工审核的候选清单，审核通过后由人手动并入 evals/*_cases.json 或补知识库。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select

from app.db.mysql import session_scope
from app.db.models import Feedback, HandoffLog, RagLog, ToolLog

TOOL_ERROR_STATUSES = ("error", "bad_input")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_feedback_candidates(limit: int = 200) -> List[Dict[str, Any]]:
    """负反馈 → 意图纠错 / grounding 纠错候选。"""
    out: List[Dict[str, Any]] = []
    with session_scope() as db:
        rows = db.execute(
            select(Feedback).where(Feedback.rating == -1)
            .order_by(Feedback.id.desc()).limit(limit)
        ).scalars()
        for f in rows:
            if not f.message:
                continue
            out.append({
                "source": "feedback",
                "session_id": f.session_id,
                "turn_index": f.turn_index,
                "message": f.message,
                "routed_intent": f.intent,
                "category": f.category,
                "correction": f.correction,
                "feedback_id": f.id,
            })
    return out


def collect_rag_gap_candidates(limit: int = 200) -> List[Dict[str, Any]]:
    """RAG 未命中的查询 → 知识库缺口候选（提示补录该主题文档）。"""
    out: List[Dict[str, Any]] = []
    with session_scope() as db:
        rows = db.execute(
            select(RagLog).where(RagLog.need_fallback.is_(True))
            .order_by(RagLog.id.desc()).limit(limit)
        ).scalars()
        for r in rows:
            q = (r.query or "").strip()
            if not q:
                continue
            out.append({
                "source": "rag_fallback",
                "query": q,
                "channel": r.channel,
                "suggestion": "知识库未命中，考虑补录该主题文档",
            })
    return out


def collect_tool_error_candidates(limit: int = 200) -> List[Dict[str, Any]]:
    """工具异常调用 → 工具参数/实现问题候选。"""
    out: List[Dict[str, Any]] = []
    with session_scope() as db:
        rows = db.execute(
            select(ToolLog).where(ToolLog.status.in_(TOOL_ERROR_STATUSES))
            .order_by(ToolLog.id.desc()).limit(limit)
        ).scalars()
        for r in rows:
            out.append({
                "source": "tool_error",
                "session_id": r.session_id,
                "turn_index": r.turn_index,
                "tool_name": r.tool_name,
                "params_digest": r.params_digest,
                "status": r.status,
            })
    return out


def collect_escalation_candidates(limit: int = 200) -> List[Dict[str, Any]]:
    """转人工工单 → 自助链路未解决的高优先级 badcase。"""
    out: List[Dict[str, Any]] = []
    with session_scope() as db:
        rows = db.execute(
            select(HandoffLog).order_by(HandoffLog.id.desc()).limit(limit)
        ).scalars()
        for r in rows:
            out.append({
                "source": "handoff",
                "session_id": r.session_id,
                "trigger_rule": r.trigger_rule,
                "ticket_id": r.ticket_id,
            })
    return out


def collect_candidates() -> Dict[str, Any]:
    """聚合全部候选，返回可落盘为 JSON 的字典。"""
    feedback = collect_feedback_candidates()
    rag = collect_rag_gap_candidates()
    tool = collect_tool_error_candidates()
    handoff = collect_escalation_candidates()
    return {
        "generated_at": _now_iso(),
        "note": "候选清单待人工审核后再并入 evals/*_cases.json 或补录知识库，不自动重训。",
        "sources": {
            "feedback_negative": len(feedback),
            "rag_fallback": len(rag),
            "tool_error": len(tool),
            "handoff": len(handoff),
        },
        "candidates": {
            "feedback": feedback,
            "rag_gaps": rag,
            "tool_errors": tool,
            "escalations": handoff,
        },
    }
