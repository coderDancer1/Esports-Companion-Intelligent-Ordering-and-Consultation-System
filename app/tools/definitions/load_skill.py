"""工具：加载 skill 正文与依赖工具列表。"""
from __future__ import annotations

from app.skills.loader import load_skill
from app.tools.errors import ToolResult, empty, error, success


async def run(ctx, skill_name: str) -> ToolResult:
    try:
        info = load_skill(skill_name)
        if not info.get("found"):
            return empty()
        ctx.loaded_skills.add(skill_name)
        ctx.injected_tools.update(info.get("dependent_tools", []))
        return success({"content": info["content"], "dependent_tools": info["dependent_tools"]})
    except Exception as e:  # noqa: BLE001
        return error("load_skill_failed", str(e))
