"""BaseExpert：统一返回结构、工具调用日志、失败回退骨架。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.orchestrator.log_writer import write_tool_log


@dataclass
class ExpertConfig:
    max_steps: int
    fallback: Dict[str, str]


class BaseExpert:
    config: ExpertConfig = ExpertConfig(max_steps=1, fallback={})

    async def __call__(self, ctx, **kw) -> Dict[str, Any]:
        raise NotImplementedError


def log_tool(ctx, tool_name: str, params_digest: str = "", status: str = "success") -> None:
    write_tool_log(ctx, tool_name, params_digest, status)


def result(reply: str, cards: Optional[list] = None, ticket_id: Optional[str] = None,
           handoff_to_human: bool = False, detected_intent_change: Optional[str] = None,
           clarify_options: Optional[list] = None, **extra) -> Dict[str, Any]:
    out: Dict[str, Any] = {"reply": reply, "handoff_to_human": handoff_to_human}
    if cards is not None:
        out["cards"] = cards
    if ticket_id:
        out["ticket_id"] = ticket_id
    if detected_intent_change:
        out["detected_intent_change"] = detected_intent_change
    if clarify_options:
        out["clarify_options"] = clarify_options
    out.update(extra)
    return out
