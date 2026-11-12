"""POST /feedback：用户对某一轮答复打标签（👍/👎 + 可选纠错）。

这是「数据飞轮」的显式采集入口——把线上真实反馈沉淀进 feedback 表，
再由 `app/flywheel.py` 归集成候选评测样例，供人工审核后并入评测集。
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.admin import require_admin
from app.db.mysql import session_scope
from app.db.models import Feedback, RouteLog
from app.security.auth import AuthUser, get_auth_user

router = APIRouter()

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_EVAL_DIR = os.path.join(_ROOT, "evals")
_VALID_INTENTS = {"recommend", "order", "complaint", "knowledge", "chitchat", "human"}


class FeedbackRequest(BaseModel):
    session_id: str
    turn_index: int
    rating: int  # +1 好 / 0 中性 / -1 差
    correction: Optional[str] = None
    category: Optional[str] = None  # intent / grounding / knowledge_gap / other


def _lookup_message(session_id: str, turn_index: int) -> str:
    """从原文归档回捞该轮用户输入（best-effort，取不到则留空）。"""
    try:
        from app.memory import raw_store
        res = raw_store.get([f"{session_id}:{turn_index}:user"])
        for m in res.get("messages", []):
            if m.get("role") == "user":
                return m.get("content", "")
    except Exception:  # noqa: BLE001
        pass
    return ""


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest, auth: AuthUser = Depends(get_auth_user)):
    if body.rating not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="rating_must_be_-1_0_1")

    intent = ""
    try:
        with session_scope() as db:
            intent = db.execute(
                select(RouteLog.intent).where(
                    RouteLog.session_id == body.session_id,
                    RouteLog.turn_index == body.turn_index,
                ).order_by(RouteLog.id.desc()).limit(1)
            ).scalar() or ""
    except Exception:  # noqa: BLE001
        pass

    message = _lookup_message(body.session_id, body.turn_index)

    with session_scope() as db:
        db.add(Feedback(
            session_id=body.session_id,
            turn_index=body.turn_index,
            user_id=auth.user_id,
            message=message,
            intent=intent,
            rating=body.rating,
            category=(body.category or "").strip(),
            correction=(body.correction or "").strip(),
        ))
    return {"ok": True, "session_id": body.session_id, "turn_index": body.turn_index}


@router.get("/feedback")
async def list_feedback(auth: AuthUser = Depends(get_auth_user)):
    with session_scope() as db:
        rows = db.execute(
            select(Feedback).where(Feedback.user_id == auth.user_id)
            .order_by(Feedback.id.desc()).limit(50)
        ).scalars()
        return {"items": [{
            "id": f.id, "session_id": f.session_id, "turn_index": f.turn_index,
            "message": f.message, "intent": f.intent, "rating": f.rating,
            "category": f.category, "correction": f.correction, "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        } for f in rows]}


class Promote(BaseModel):
    target: str  # "intent_cases" | "rag_cases"
    intent: Optional[str] = None  # 仅 target=intent_cases 需要


class ReviewRequest(BaseModel):
    feedback_ids: List[int]
    decision: str  # "reviewed" | "ignored"
    promote: Optional[Promote] = None


def _promote_intent_cases(messages: List[str], intent: str) -> int:
    """把负反馈的原始消息作为意图评测样例并入 intent_cases.json（按 message 去重）。"""
    path = os.path.join(_EVAL_DIR, "intent_cases.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    existing = {c.get("message") for c in data["cases"]}
    added = 0
    for msg in messages:
        if not msg or msg in existing:
            continue
        data["cases"].append({"message": msg, "intent": intent, "note": "飞轮回流：来自负反馈"})
        existing.add(msg)
        added += 1
    if added:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return added


def _promote_rag_cases(messages: List[str]) -> int:
    """把知识库缺口查询作为负例并入 rag_cases.json（按 query 去重）。"""
    path = os.path.join(_EVAL_DIR, "rag_cases.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    existing = {c.get("query") for c in data["cases"]}
    added = 0
    for msg in messages:
        if not msg or msg in existing:
            continue
        data["cases"].append({"query": msg, "expect_found": False, "note": "飞轮回流：知识库缺口"})
        existing.add(msg)
        added += 1
    if added:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return added


@router.post("/feedback/review")
async def review_feedback(body: ReviewRequest, _admin=Depends(require_admin)):
    """人工审核：标记 reviewed/ignored，并可一键把通过项并入对应评测集。"""
    if body.decision not in ("reviewed", "ignored"):
        raise HTTPException(status_code=400, detail="decision_must_be_reviewed_or_ignored")

    with session_scope() as db:
        rows = db.execute(
            select(Feedback).where(Feedback.id.in_(body.feedback_ids))
        ).scalars().all()
        messages = [(r.message or "").strip() for r in rows]
        for r in rows:
            r.status = body.decision

    promoted = 0
    if body.promote:
        if body.decision != "reviewed":
            raise HTTPException(status_code=400, detail="promote_requires_reviewed")
        target = body.promote.target
        if target == "intent_cases":
            intent = body.promote.intent
            if intent not in _VALID_INTENTS:
                raise HTTPException(status_code=400, detail="invalid_intent")
            promoted = _promote_intent_cases(messages, intent)
        elif target == "rag_cases":
            promoted = _promote_rag_cases(messages)
        else:
            raise HTTPException(status_code=400, detail="invalid_target")

    return {"ok": True, "updated": len(rows), "promoted": promoted}
