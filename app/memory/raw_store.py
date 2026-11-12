"""原文归档：Chroma memory_raw 逐条按 message_id 归档，不参与语义检索。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.chroma_client import COLLECTION_MEMORY_RAW
from app.db.lock import now_ts
from app.db.vector_store import get_vector_store


def write_turn(user_id: str, session_id: str, turn_index: int, user_msg: str,
               reply: str, tool_calls: Optional[list] = None) -> None:
    store = get_vector_store()
    store.upsert(
        COLLECTION_MEMORY_RAW,
        ids=[f"{session_id}:{turn_index}:user", f"{session_id}:{turn_index}:assistant"],
        documents=[user_msg, reply],
        metadatas=[
            {"user_id": user_id, "session_id": session_id, "message_id": f"{session_id}:{turn_index}:user",
             "role": "user", "turn_index": turn_index, "created_at": now_ts()},
            {"user_id": user_id, "session_id": session_id, "message_id": f"{session_id}:{turn_index}:assistant",
             "role": "assistant", "turn_index": turn_index, "created_at": now_ts()},
        ],
    )


def get(message_ids: List[str]) -> Dict[str, Any]:
    """按 message_id 精确回捞原文。"""
    store = get_vector_store()
    res = store.get(COLLECTION_MEMORY_RAW, message_ids)
    messages = []
    for i, mid in enumerate(res["ids"]):
        meta = res["metadatas"][i] if i < len(res["metadatas"]) else {}
        messages.append({"message_id": mid, "role": meta.get("role", ""),
                         "content": res["documents"][i] if i < len(res["documents"]) else "",
                         "turn_index": meta.get("turn_index", 0)})
    return {"messages": messages}
