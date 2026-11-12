"""GET /healthz：探活 Redis/MySQL/Chroma/bm25/LLM 连通性。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz():
    status = {"redis": "ok", "mysql": "ok", "chroma": "ok", "bm25": "ok", "llm": "ok"}

    try:
        from app.db.redis_client import get_redis
        get_redis().set("healthz", "1", ex=10)
    except Exception:  # noqa: BLE001
        status["redis"] = "error"

    try:
        from sqlalchemy import text
        from app.db.mysql import session_scope
        with session_scope() as db:
            db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        status["mysql"] = "error"

    try:
        from app.db.vector_store import get_vector_store
        get_vector_store()
    except Exception:  # noqa: BLE001
        status["chroma"] = "error"

    try:
        from app.rag.indexer import get_bm25
        get_bm25()
    except Exception:  # noqa: BLE001
        status["bm25"] = "error"

    from app.llm.client import is_llm_available
    status["llm"] = "ok" if is_llm_available() else "mock"

    overall = "ok" if all(v in ("ok", "mock") for v in status.values()) else "degraded"
    return {"status": overall, **status}
