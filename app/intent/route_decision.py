"""RouteDecision：意图分类结果数据结构。"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


class RouteDecision(BaseModel):
    intent: Literal["recommend", "order", "complaint", "knowledge", "chitchat", "human", "unknown"]
    confidence: float
    reason: str
    route_source: Literal["rule", "sticky", "embedding", "llm", "clarify_resolved"]
    clarify_options: Optional[List[str]] = None
