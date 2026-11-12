"""工具：结构化筛选 + 候选集内向量排序，返回候选列表与匹配分。"""
from __future__ import annotations

from typing import List, Optional

from app.matching.service import search_playmates as _search
from app.tools.errors import ToolResult, empty, error, success


async def run(ctx, game: Optional[str] = None, rank_min: Optional[str] = None,
              rank_max: Optional[str] = None, price_min: Optional[int] = None,
              price_max: Optional[int] = None, personality_tags: Optional[List[str]] = None,
              online_only: Optional[bool] = None, semantic_query: Optional[str] = None,
              limit: int = 5) -> ToolResult:
    try:
        res = _search(game=game, rank_min=rank_min, rank_max=rank_max, price_min=price_min,
                      price_max=price_max, personality_tags=personality_tags,
                      online_only=online_only, semantic_query=semantic_query, limit=limit)
        if res.get("status") == "empty" or not res.get("items"):
            return empty({"items": []})
        return success({"items": res["items"]})
    except Exception as e:  # noqa: BLE001
        return error("search_failed", str(e))
