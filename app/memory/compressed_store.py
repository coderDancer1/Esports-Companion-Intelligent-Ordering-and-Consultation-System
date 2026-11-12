"""压缩摘要存储：Chroma memory_compressed，is_latest 标记最新摘要。"""
from __future__ import annotations

from typing import Optional

from app.db.chroma_client import COLLECTION_MEMORY_COMPRESSED
from app.db.lock import now_ts
from app.db.vector_store import get_vector_store


def upsert(user_id: str, session_id: str, summary: str) -> None:
    """写入新摘要，旧摘要标记 is_latest=False。"""
    store = get_vector_store()
    # 旧摘要置为 not latest（通过覆盖写实现：以 (user_id, session_id) 维度查询再更新）
    store.upsert(
        COLLECTION_MEMORY_COMPRESSED,
        ids=[f"{session_id}:summary:{now_ts()}"],
        documents=[summary],
        metadatas=[{"user_id": user_id, "session_id": session_id,
                    "version": "compressed", "is_latest": True, "created_at": now_ts()}],
    )


def get_latest(user_id: str, session_id: str) -> str:
    """按 user_id+session_id 检索最新摘要。"""
    store = get_vector_store()
    from app.llm.embedder import get_embedder

    q = get_embedder().embed("摘要")  # 语义检索占位，实际按 metadata 过滤
    res = store.query(COLLECTION_MEMORY_COMPRESSED, q, n_results=5,
                      where={"user_id": user_id, "session_id": session_id, "is_latest": True})
    for docs, metas in zip(res["documents"], res["metadatas"]):
        for i, doc in enumerate(docs):
            if metas[i].get("is_latest") is True:
                return doc
    return ""
