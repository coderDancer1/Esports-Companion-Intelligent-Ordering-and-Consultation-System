"""陪玩师匹配：结构化过滤（MySQL）→ 候选集内向量排序 → 热点缓存。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.db.chroma_client import COLLECTION_PLAYMATE_PROFILES
from app.db.mysql import session_scope
from app.db.models import Playmate
from app.db.redis_client import get_redis, json_dumps, json_loads
from app.db.vector_store import get_vector_store
from app.llm.embedder import cosine, get_embedder

RANK_ORDER = ["青铜", "白银", "黄金", "铂金", "钻石", "大师", "宗师", "王者", "神话", "无畏"]


def _rank_idx(rank: str) -> int:
    if rank in RANK_ORDER:
        return RANK_ORDER.index(rank)
    # 兼容数字段位
    try:
        return int(rank)
    except (ValueError, TypeError):
        return 0


def _playmate_dict(p: Playmate) -> Dict[str, Any]:
    return {
        "id": p.id, "nickname": p.nickname, "game": p.game, "rank": p.rank,
        "price_per_hour": p.price_per_hour, "personality_tags": p.personality_tags or [],
        "heroes": p.heroes or [], "intro": p.intro, "rating": p.rating,
        "order_count": p.order_count, "ontime_rate": p.ontime_rate,
        "online_status": p.online_status,
    }


def _structured_filter(game: Optional[str], rank_min: Optional[str], rank_max: Optional[str],
                       price_min: Optional[int], price_max: Optional[int],
                       personality_tags: Optional[List[str]],
                       online_only: Optional[bool]) -> List[Dict[str, Any]]:
    with session_scope() as db:
        stmt = select(Playmate)
        if game:
            stmt = stmt.where(Playmate.game == game)
        if price_min is not None:
            stmt = stmt.where(Playmate.price_per_hour >= price_min)
        if price_max is not None:
            stmt = stmt.where(Playmate.price_per_hour <= price_max)
        if online_only:
            stmt = stmt.where(Playmate.online_status.is_(True))
        items = [_playmate_dict(p) for p in db.execute(stmt).scalars()]

    if rank_min is not None or rank_max is not None:
        lo = _rank_idx(rank_min) if rank_min is not None else 0
        hi = _rank_idx(rank_max) if rank_max is not None else len(RANK_ORDER) - 1
        items = [it for it in items if lo <= _rank_idx(it["rank"]) <= hi]

    if personality_tags:
        tags = set(personality_tags)
        items = [it for it in items if tags & set(it["personality_tags"])]
        # 按命中标签数排序（多命中的优先）
        items.sort(key=lambda it: len(tags & set(it["personality_tags"])), reverse=True)

    return items


def _vector_rank(candidates: List[Dict[str, Any]], semantic_query: str) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    store = get_vector_store()
    ids = [c["id"] for c in candidates]
    if len(candidates) <= 500:
        q = get_embedder().embed(semantic_query)
        res = store.query(COLLECTION_PLAYMATE_PROFILES, q, n_results=len(ids),
                          where={"playmate_id": {"$in": ids}})
        sim_map = {}
        for batch_ids, batch_sims in zip(res["ids"], res["similarities"]):
            for cid, sim in zip(batch_ids, batch_sims):
                sim_map[cid] = sim
    else:
        # 候选集过大时走应用层余弦
        emb = get_embedder()
        q = emb.embed(semantic_query)
        sim_map = {}
        for c in candidates:
            from app.matching.profile_index import profile_text
            sim_map[c["id"]] = cosine(q, emb.embed(profile_text(c)))
    for c in candidates:
        c["_semantic_score"] = sim_map.get(c["id"], 0.0)
    candidates.sort(key=lambda c: c["_semantic_score"], reverse=True)
    return candidates


def search_playmates(game: Optional[str] = None, rank_min: Optional[str] = None,
                     rank_max: Optional[str] = None, price_min: Optional[int] = None,
                     price_max: Optional[int] = None, personality_tags: Optional[List[str]] = None,
                     online_only: Optional[bool] = None, semantic_query: Optional[str] = None,
                     limit: int = 5) -> Dict[str, Any]:
    """结构化过滤 + 语义排序，返回 {status, items}。"""
    # 热点缓存
    cache_key = f"playmate:hot:{game or 'all'}:{price_min or 0}:{price_max or 9999}:{'-'.join(sorted(personality_tags or []))}"
    r = get_redis()
    if semantic_query is None:
        cached = json_loads(r.get(cache_key))
        if cached is not None:
            return {"status": "success", "items": cached[:limit]}

    candidates = _structured_filter(game, rank_min, rank_max, price_min, price_max,
                                    personality_tags, online_only)
    if not candidates:
        return {"status": "empty", "items": []}

    if semantic_query:
        candidates = _vector_rank(candidates, semantic_query)
    else:
        # 无语义查询时按评分/接单量排序
        candidates.sort(key=lambda c: (c["rating"], c["order_count"], -c["price_per_hour"]), reverse=True)

    items = []
    for c in candidates[:limit]:
        item = {k: v for k, v in c.items() if not k.startswith("_")}
        sem = float(c.get("_semantic_score", 0.0))
        # 哈希向量余弦在短查询下偏弱，语义分过低时退回结构化相关度
        if sem < 0.3:
            sem = 0.5 + min(0.4, (float(c.get("rating") or 0.0) / 5.0) * 0.4)
        item["match_score"] = round(sem, 4)
        items.append(item)

    if semantic_query is None and items:
        r.set(cache_key, json_dumps(items), ex=180)
    return {"status": "success", "items": items}
