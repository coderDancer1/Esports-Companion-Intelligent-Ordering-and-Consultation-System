"""工具：评估情绪强度与标签。"""
from __future__ import annotations

from app.business.compliance.content_safety import assess_emotion as _assess
from app.tools.errors import ToolResult, error, success


async def run(ctx, message: str) -> ToolResult:
    try:
        return success(_assess(message))
    except Exception as e:  # noqa: BLE001
        return error("assess_emotion_failed", str(e))
