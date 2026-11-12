"""AgentContext：贯穿一轮对话的上下文容器。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class AgentContext:
    user_id: str
    session_id: str
    message: str
    turn_index: int
    system_prompt: str = ""
    user_profile: Dict[str, Any] = field(default_factory=dict)
    compressed_summary: str = ""
    recent_messages: List[Dict[str, Any]] = field(default_factory=list)
    structured_state: Dict[str, Any] = field(default_factory=dict)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    handoff_count: int = 0
    route_decision: Optional[Dict[str, Any]] = None
    loaded_skills: Set[str] = field(default_factory=set)
    injected_tools: Set[str] = field(default_factory=set)
    trace_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_minor: bool = False
