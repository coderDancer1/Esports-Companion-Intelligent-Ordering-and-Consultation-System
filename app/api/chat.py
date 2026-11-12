"""POST /chat 与 /chat/stream：统一对话入口，内部经 Orchestrator 分派。"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.orchestrator.core import get_orchestrator
from app.security.auth import AuthUser, get_auth_user
from app.security.guard import ensure_user_id_match

router = APIRouter()


class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    session_id: str
    message: str
    client_ts: Optional[int] = None


async def _check(body: ChatRequest, auth: AuthUser) -> str:
    # 安全红线：body.user_id 与 token 不一致 → 403；业务一律用 auth.user_id
    await ensure_user_id_match(auth, body.user_id)
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="message_required")
    return body.message.strip()


@router.post("/chat")
async def chat(body: ChatRequest, auth: AuthUser = Depends(get_auth_user)):
    message = await _check(body, auth)
    return await get_orchestrator().handle(auth, body.session_id, message)


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, auth: AuthUser = Depends(get_auth_user)):
    """SSE 流式对话：逐段产出回复文本，最后以 {'type':'done', ...} 携带完整响应。"""
    message = await _check(body, auth)

    async def event_stream():
        async for ev in get_orchestrator().handle_stream(auth, body.session_id, message):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
