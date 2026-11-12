"""意图粘性：延续词/失效词判断，仅 recommend/order 生效；失效词优先于延续词。"""
from __future__ import annotations

from typing import Optional

CONTINUATIONS = {"再", "还", "换", "另一个", "便宜点", "贵了", "不要这个", "就它了",
                 "类似的", "其他的", "快一点", "慢一点", "来个", "有没有别的"}
INVALIDATORS = {"算了", "投诉", "人工", "客服", "退款", "不想要了", "取消", "举报"}


def check(message: str, last_intent: Optional[str]) -> Optional[str]:
    if last_intent not in {"recommend", "order"}:
        return None
    if any(w in message for w in INVALIDATORS):
        return None
    if any(w in message for w in CONTINUATIONS):
        return last_intent
    return None
