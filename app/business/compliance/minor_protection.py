"""未成年人保护：充值/打赏限制、时段限制、禁陪玩师注册。"""
from __future__ import annotations

from datetime import datetime, timezone

# 未成年人允许使用的时段（北京时间 8:00-22:00，简化按 UTC+8 处理）
_MINOR_START = 8
_MINOR_END = 22


def is_minor_allowed_hour() -> bool:
    hour = (datetime.now(timezone.utc).hour + 8) % 24
    return _MINOR_START <= hour < _MINOR_END


def check_action(is_minor: bool, action: str) -> Dict:
    """下单/充值/打赏等资金操作前调用。"""
    if not is_minor:
        return {"allowed": True, "reason": "ok"}
    if action in {"order", "recharge", "tip"}:
        if not is_minor_allowed_hour():
            return {"allowed": False, "reason": "minor_restricted"}
        return {"allowed": False, "reason": "minor_restricted"}
    return {"allowed": True, "reason": "ok"}


def can_register_playmate(is_minor: bool) -> bool:
    """未成年人禁止注册为陪玩师。"""
    return not is_minor
