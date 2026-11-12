"""Chroma 集合句柄：定义四个 collection 名称并提供初始化/访问入口。"""
from __future__ import annotations


COLLECTION_MEMORY_COMPRESSED = "memory_compressed"
COLLECTION_MEMORY_RAW = "memory_raw"
COLLECTION_KNOWLEDGE_BASE = "knowledge_base"
COLLECTION_PLAYMATE_PROFILES = "playmate_profiles"

ALL_COLLECTIONS = [
    COLLECTION_MEMORY_COMPRESSED,
    COLLECTION_MEMORY_RAW,
    COLLECTION_KNOWLEDGE_BASE,
    COLLECTION_PLAYMATE_PROFILES,
]


def init_chroma() -> None:
    """启动时初始化向量存储（进程内实现为惰性创建，此处仅触发单例）。"""
    from app.db.vector_store import get_vector_store

    get_vector_store()


def get_chroma():
    from app.db.vector_store import get_vector_store

    return get_vector_store()
