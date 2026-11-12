"""短期记忆：Redis List 存储逐轮消息 + meta Hash。

Key：session:{session_id}:messages（List）
Meta：session:{session_id}:meta（Hash）
summary 消息 stable_prefix=true，位于 List 首元素。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.db.lock import now_ts
from app.db.redis_client import get_redis, json_dumps, json_loads


def _msg_key(session_id: str) -> str:
    return f"session:{session_id}:messages"


def _meta_key(session_id: str) -> str:
    return f"session:{session_id}:meta"


def _msg(role: str, content: str, tool_calls=None, stable_prefix: bool = False) -> str:
    return json_dumps({
        "role": role, "content": content, "tool_calls": tool_calls,
        "created_at": now_ts(), "stable_prefix": stable_prefix,
    })


def append_user(session_id: str, message: str) -> None:
    get_redis().rpush(_msg_key(session_id), _msg("user", message))


def append_assistant(session_id: str, reply: str, tool_calls=None) -> None:
    get_redis().rpush(_msg_key(session_id), _msg("assistant", reply, tool_calls))


def get_recent(session_id: str, n: int = 5) -> List[Dict[str, Any]]:
    raw = get_redis().lrange(_msg_key(session_id), -n, -1)
    return [json_loads(r) for r in raw if json_loads(r)]


def get_all(session_id: str) -> List[Dict[str, Any]]:
    raw = get_redis().lrange(_msg_key(session_id), 0, -1)
    return [json_loads(r) for r in raw if json_loads(r)]


def rebuild_with_summary(session_id: str, summary: str, keep: List[Dict[str, Any]]) -> None:
    """DEL + 重建：summary 在头部（stable_prefix=true），随后是最近 keep 条原文。"""
    r = get_redis()
    key = _msg_key(session_id)
    r.delete(key)
    r.rpush(key, _msg("summary", summary, stable_prefix=True))
    for m in keep:
        r.rpush(key, json_dumps(m))


def update_meta(session_id: str, mapping: Dict[str, Any]) -> None:
    r = get_redis()
    key = _meta_key(session_id)
    payload: Dict[str, str] = {}
    for k, v in mapping.items():
        payload[k] = json_dumps(v) if not isinstance(v, str) else v
    r.hset(key, payload)


def get_meta(session_id: str) -> Dict[str, str]:
    return get_redis().hgetall(_meta_key(session_id))


def get_meta_field(session_id: str, field: str) -> Optional[str]:
    return get_redis().hget(_meta_key(session_id), field)
