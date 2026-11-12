"""画像增量更新：LLM 抽取变化字段（ProfileDelta 严格约束），只写变化项。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.llm.client import complete, extract_json, is_llm_available
from app.memory import profile as profile_store

_GAMES = ["英雄联盟", "lol", "无畏契约", "valorant", "瓦", "三角洲行动", "三角洲", "绝地求生", "csgo"]
_PERSONALITY = ["温柔", "带飞", "技术", "教学", "搞笑", "御姐", "奶音", "声音好听", "心态好"]


class ProfileDelta(BaseModel):
    preferred_price_min: Optional[int] = None
    preferred_price_max: Optional[int] = None
    personality_pref: Optional[List[str]] = None
    main_games: Optional[List[str]] = None
    last_order_game: Optional[str] = None


def _mock_extract(messages: List[Dict[str, Any]]) -> ProfileDelta:
    text = "\n".join(m.get("content", "") for m in messages)
    delta: Dict[str, Any] = {}

    m = re.search(r"预算\s*(\d+)\s*以内", text)
    if m:
        delta["preferred_price_max"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:元|块)(?:/时|每小时|一小时)?", text)
    if m and "preferred_price_max" not in delta:
        delta["preferred_price_max"] = int(m.group(1))

    prefs = [p for p in _PERSONALITY if p in text]
    if prefs:
        delta["personality_pref"] = prefs

    games = [g for g in _GAMES if g.lower() in text.lower()]
    if games:
        delta["main_games"] = games
        delta["last_order_game"] = games[-1]

    return ProfileDelta(**delta)


async def _llm_extract(messages: List[Dict[str, Any]]) -> ProfileDelta:
    convo = "\n".join(f"{m.get('role')}: {m.get('content','')[:200]}" for m in messages)
    resp = await complete(
        [{"role": "user", "content":
          f"只保存稳定偏好与事实，不做关键词抽取，新值覆盖旧值，只输出变化字段。\n\n"
          f"请只输出一个 JSON 对象（无变化时输出 {{}}），可选字段："
          f"preferred_price_min(整数)、preferred_price_max(整数)、"
          f"personality_pref(字符串数组)、main_games(字符串数组)、last_order_game(字符串)。"
          f"不要输出任何解释或多余文本。\n\n对话：\n{convo}"}],
        max_tokens=256, temperature=0.0,
    )
    data = extract_json(resp.get("content"))
    if not data:
        return ProfileDelta()
    try:
        return ProfileDelta(**data)
    except Exception:  # noqa: BLE001
        return ProfileDelta()


async def update(user_id: str, messages: List[Dict[str, Any]]) -> None:
    """压缩时增量更新画像；只写变化字段。"""
    if is_llm_available():
        delta = await _llm_extract(messages)
    else:
        delta = _mock_extract(messages)
    changes = delta.model_dump(exclude_none=True)
    if changes:
        profile_store.update(user_id, changes)
