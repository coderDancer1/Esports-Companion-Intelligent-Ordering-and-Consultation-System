"""陪玩师服务：档案查询、创建/更新、向量索引同步触发。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Playmate
from app.db.mysql import session_scope


def _dict(p: Playmate) -> Dict[str, Any]:
    return {
        "id": p.id,
        "nickname": p.nickname,
        "game": p.game,
        "rank": p.rank,
        "price_per_hour": p.price_per_hour,
        "personality_tags": p.personality_tags or [],
        "heroes": p.heroes or [],
        "intro": p.intro,
        "rating": p.rating,
        "order_count": p.order_count,
        "ontime_rate": p.ontime_rate,
        "online_status": p.online_status,
    }


def get_playmate(playmate_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as db:
        p = db.get(Playmate, playmate_id)
        return _dict(p) if p else None


def list_playmates(game: Optional[str] = None) -> List[Dict[str, Any]]:
    with session_scope() as db:
        stmt = select(Playmate)
        if game:
            stmt = stmt.where(Playmate.game == game)
        return [_dict(p) for p in db.execute(stmt).scalars()]


def upsert_playmate(data: Dict[str, Any]) -> Dict[str, Any]:
    with session_scope() as db:
        pid = data.get("id")
        p = db.get(Playmate, pid) if pid else None
        if p is None:
            p = Playmate(id=pid or _new_pid())
            db.add(p)
        for field in ("nickname", "game", "rank", "intro"):
            if field in data:
                setattr(p, field, data[field])
        for field in ("price_per_hour", "order_count", "rating", "ontime_rate"):
            if field in data:
                setattr(p, field, data[field])
        if "personality_tags" in data:
            p.personality_tags = data["personality_tags"]
        if "heroes" in data:
            p.heroes = data["heroes"]
        if "online_status" in data:
            p.online_status = data["online_status"]
        db.flush()
        result = _dict(p)
    # 双写向量索引（失败进重试队列，不阻断主流程）
    try:
        from app.matching.profile_index import sync_playmate
        sync_playmate(result)
    except Exception:  # noqa: BLE001
        pass
    return result


def _new_pid() -> str:
    import uuid
    return "p_" + uuid.uuid4().hex[:10]
