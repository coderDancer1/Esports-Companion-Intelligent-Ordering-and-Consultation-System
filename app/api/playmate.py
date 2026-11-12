"""陪玩师 HTTP 接口：搜索、详情。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query

from app.business.playmate.service import get_playmate
from app.matching.service import search_playmates
from app.security.auth import get_auth_user

router = APIRouter()


@router.get("/playmates/search")
async def search(game: Optional[str] = None, rank_min: Optional[str] = None,
                 rank_max: Optional[str] = None, price_min: Optional[int] = None,
                 price_max: Optional[int] = None, personality_tags: Optional[str] = None,
                 online_only: Optional[bool] = None, page: int = 1, size: int = 20,
                 semantic_query: Optional[str] = None, _auth=Depends(get_auth_user)):
    tags = [t.strip() for t in personality_tags.split(",")] if personality_tags else None
    res = search_playmates(game=game, rank_min=rank_min, rank_max=rank_max, price_min=price_min,
                           price_max=price_max, personality_tags=tags, online_only=online_only,
                           semantic_query=semantic_query, limit=size)
    return {"total": len(res.get("items", [])), "items": res.get("items", [])}


@router.get("/playmates/{playmate_id}")
async def detail(playmate_id: str, _auth=Depends(get_auth_user)):
    p = get_playmate(playmate_id)
    if not p:
        raise HTTPException(status_code=404, detail="playmate_not_found")
    return p
