"""工具：取陪玩师完整档案。"""
from __future__ import annotations

from app.business.playmate.service import get_playmate
from app.tools.errors import ToolResult, empty, error, success


async def run(ctx, playmate_id: str) -> ToolResult:
    try:
        p = get_playmate(playmate_id)
        if not p:
            return empty()
        return success(p)
    except Exception as e:  # noqa: BLE001
        return error("get_playmate_failed", str(e))
