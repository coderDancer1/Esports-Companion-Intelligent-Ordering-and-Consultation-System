"""工具：取用户画像。"""
from __future__ import annotations

from app.memory import profile as profile_store
from app.tools.errors import ToolResult, error, success


async def run(ctx) -> ToolResult:
    try:
        return success(profile_store.get(ctx.user_id))
    except Exception as e:  # noqa: BLE001
        return error("get_profile_failed", str(e))
