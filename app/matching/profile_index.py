"""陪玩师向量索引：档案变更双写 MySQL + 向量库，失败进重试队列。"""
from __future__ import annotations

from typing import Any, Dict, List

from app.db.chroma_client import COLLECTION_PLAYMATE_PROFILES
from app.db.vector_store import get_vector_store

_retry_queue: List[Dict[str, Any]] = []


def profile_text(p: Dict[str, Any]) -> str:
    tags = " ".join(p.get("personality_tags") or [])
    heroes = " ".join(p.get("heroes") or [])
    return (f"{p.get('nickname','')} | {p.get('game','')} | {p.get('rank','')} | "
            f"{tags} | {p.get('intro','')} | 擅长:{heroes}")


def sync_playmate(playmate: Dict[str, Any]) -> None:
    """将单个陪玩师档案写入向量库。失败入队重试。"""
    pid = playmate["id"]
    store = get_vector_store()
    try:
        store.upsert(
            COLLECTION_PLAYMATE_PROFILES,
            ids=[pid],
            documents=[profile_text(playmate)],
            metadatas=[{"playmate_id": pid, "game": playmate.get("game", "")}],
        )
    except Exception:  # noqa: BLE001
        _retry_queue.append(playmate)


def rebuild(playmates: List[Dict[str, Any]]) -> int:
    """全量重建陪玩师向量索引。"""
    store = get_vector_store()
    store.delete(COLLECTION_PLAYMATE_PROFILES)
    store.upsert(
        COLLECTION_PLAYMATE_PROFILES,
        ids=[p["id"] for p in playmates],
        documents=[profile_text(p) for p in playmates],
        metadatas=[{"playmate_id": p["id"], "game": p.get("game", "")} for p in playmates],
    )
    return len(playmates)
