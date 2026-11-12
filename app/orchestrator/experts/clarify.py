"""澄清专家：低置信度时输出候选意图让用户确认（上限 2 轮）。"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.orchestrator.experts.base import result

_LABEL = {"recommend": "推荐陪玩", "order": "查询订单", "complaint": "投诉",
          "knowledge": "咨询平台规则", "human": "转人工客服"}


async def clarify_expert(ctx, clarify_options: Optional[List[str]] = None) -> Dict:
    options = clarify_options or ["recommend", "order"]
    names = "、".join(_LABEL.get(o, o) for o in options)
    return result(f"你是想让我帮你{names}？", clarify_options=options)
