"""推荐专家：自然语言→结构化筛选条件→search_playmates→可解释话术。"""
from __future__ import annotations

import re
from typing import Dict, List

from app.matching.service import RANK_ORDER, search_playmates
from app.orchestrator.experts.base import log_tool, result

_GAME_MAP = {"无畏契约": "valorant", "valorant": "valorant", "瓦": "valorant",
             "英雄联盟": "lol", "lol": "lol", "三角洲行动": "delta", "三角洲": "delta",
             "绝地求生": "pubg", "吃鸡": "pubg", "csgo": "csgo", "cs": "csgo"}
_TAGS = ["温柔", "带飞", "技术", "教学", "搞笑", "御姐", "奶音", "声音好听", "心态好"]


def _extract_filters(message: str) -> Dict:
    filters: Dict = {}
    low = message.lower()
    text = message
    for name, code in _GAME_MAP.items():
        if name in message or name.lower() in low:
            filters["game"] = code
            text = text.replace(name, " ")  # 剥离游戏名，避免"无畏契约"误匹配段位"无畏"
            break
    for rank in RANK_ORDER:
        if rank in text:
            filters["rank_min"] = rank
            filters["rank_max"] = rank
            break
    m = re.search(r"预算\s*(\d+)\s*以内", message)
    if m:
        filters["price_max"] = int(m.group(1))
    else:
        m = re.search(r"(\d+)\s*(?:元|块)(?:/时|每小时|一小时)?", message)
        if m:
            filters["price_max"] = int(m.group(1))
    tags = [t for t in _TAGS if t in message]
    if tags:
        filters["personality_tags"] = tags
    return filters


def _reason(it: Dict) -> str:
    tags = "、".join(it.get("personality_tags") or []) or "综合"
    ontime = int(round((it.get("ontime_rate") or 0) * 100))
    return (f"{it.get('rank')}段位，{tags}，近30天准时率{ontime}%，"
            f"价位{it.get('price_per_hour')}元/时")


def _filters_desc(filters: Dict) -> str:
    parts = []
    if filters.get("game"):
        parts.append(f"游戏={filters['game']}")
    if filters.get("rank_min"):
        parts.append(f"段位={filters['rank_min']}")
    if filters.get("price_max"):
        parts.append(f"预算≤{filters['price_max']}元/时")
    if filters.get("personality_tags"):
        parts.append(f"标签={','.join(filters['personality_tags'])}")
    return "；".join(parts) or "按语义匹配"


async def recommend_expert(ctx) -> Dict:
    filters = _extract_filters(ctx.message)
    res = search_playmates(
        game=filters.get("game"), rank_min=filters.get("rank_min"),
        rank_max=filters.get("rank_max"), price_max=filters.get("price_max"),
        personality_tags=filters.get("personality_tags"),
        semantic_query=ctx.message, limit=5,
    )
    log_tool(ctx, "search_playmates", str(filters), res.get("status", "success"))

    if res.get("status") == "empty" or not res.get("items"):
        return result("没有找到完全符合的陪玩师，可以试试放宽预算或段位、减少标签条件～",
                      facts={"筛选条件": _filters_desc(filters)})

    items = res["items"]
    cards = [{"type": "playmate", "id": it["id"], "nickname": it["nickname"],
              "game": it["game"], "rank": it["rank"], "price_per_hour": it["price_per_hour"],
              "personality_tags": it["personality_tags"], "match_score": it.get("match_score"),
              "reason": _reason(it)}
             for it in items]
    reply = f"给你筛了 {len(items)} 位符合的陪玩师，看看有没有合适的："
    return result(reply, cards=cards, facts={"筛选条件": _filters_desc(filters)})
