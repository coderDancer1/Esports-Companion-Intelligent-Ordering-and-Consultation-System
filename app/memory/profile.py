"""用户画像：Redis Hash，未命中回源 MySQL 并回填，字段级更新 + TTL。

Key：user:{user_id}
字段：preferred_price_min/max、personality_pref、main_games、complaint_count、
     member_level、last_order_game、preferred_playmate_ids、updated_at
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.config import get_settings
from app.db.redis_client import get_redis, json_dumps, json_loads


def _key(user_id: str) -> str:
    return f"user:{user_id}"


def get(user_id: str) -> Dict[str, Any]:
    r = get_redis()
    raw = r.hgetall(_key(user_id))
    if raw:
        out: Dict[str, Any] = {}
        for k, v in raw.items():
            if k in ("main_games", "preferred_playmate_ids", "personality_pref"):
                out[k] = json_loads(v) or []
            elif k in ("preferred_price_min", "preferred_price_max", "complaint_count", "member_level"):
                try:
                    out[k] = int(v)
                except (ValueError, TypeError):
                    out[k] = v
            else:
                out[k] = v
        return out
    # 回源 MySQL
    profile = _from_mysql(user_id)
    _write(user_id, profile)
    return profile


def _from_mysql(user_id: str) -> Dict[str, Any]:
    try:
        from app.db.mysql import session_scope
        from app.db.models import User

        with session_scope() as db:
            u = db.get(User, user_id)
            if u is None:
                return {"member_level": 0}
            return {
                "member_level": u.member_level,
                "preferred_price_min": None,
                "preferred_price_max": None,
                "personality_pref": [],
                "main_games": [],
                "complaint_count": 0,
                "last_order_game": "",
                "preferred_playmate_ids": [],
                "updated_at": 0,
            }
    except Exception:  # noqa: BLE001
        return {"member_level": 0}


def _write(user_id: str, fields: Dict[str, Any]) -> None:
    r = get_redis()
    payload: Dict[str, str] = {}
    for k, v in fields.items():
        if v is None:
            continue
        payload[k] = json_dumps(v) if isinstance(v, (list, dict)) else str(v)
    if payload:
        r.hset(_key(user_id), payload)
        r.expire(_key(user_id), get_settings().PROFILE_TTL)


def update(user_id: str, fields: Dict[str, Any]) -> None:
    """字段级更新：仅写入非 None 的变化字段。"""
    r = get_redis()
    payload: Dict[str, str] = {}
    for k, v in fields.items():
        if v is None:
            continue
        payload[k] = json_dumps(v) if isinstance(v, (list, dict)) else str(v)
    if payload:
        from app.db.lock import now_ts
        payload["updated_at"] = str(now_ts())
        r.hset(_key(user_id), payload)
        r.expire(_key(user_id), get_settings().PROFILE_TTL)
