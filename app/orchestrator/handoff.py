"""转交辅助：意图切换识别、handoff_count 阈值判定。"""
from __future__ import annotations

from typing import Optional

from app.config import get_settings

_SWITCH = {"投诉": "complaint", "举报": "complaint", "退款": "order",
           "人工": "human", "客服": "human", "真人": "human"}


def detect_intent_change(message: str) -> Optional[str]:
    """识别强切换信号（专家未捕获时的安全网）。"""
    for word, intent in _SWITCH.items():
        if word in message:
            return intent
    return None


def exceeded(handoff_count: int) -> bool:
    return handoff_count >= get_settings().HANDOFF_MAX
