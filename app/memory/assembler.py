"""上下文组装：system→画像→摘要→短期消息→当前输入→工具结果 顺序拼装。"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from app.orchestrator.context import AgentContext

BASE_SYSTEM = (
    "你是电竞陪玩平台的智能助手，负责推荐陪玩师、查询订单、处理售后与咨询。\n"
    "铁律：\n"
    "1. 你只做理解、可执行性判断与话术生成，不得直接写订单状态或操作资金。\n"
    "2. 工具返回 status=\"empty\" 表示查无结果，必须如实告知\"没有找到\"，不得编造。\n"
    "3. 工具返回 status=\"error\" 表示调用失败，必须如实说明失败，不得说成\"已处理\"。\n"
    "4. 涉及退款/改单/取消时只输出可执行性判断与参数，实际执行由后端完成。\n"
)


def build_system_prompt() -> str:
    from app.skills.loader import catalog_text

    return BASE_SYSTEM + "\n可用技能目录：\n" + catalog_text()


def build(auth, session_id: str, message: str, turn_index: int, profile: Dict[str, Any],
          summary: str, recent: List[Dict[str, Any]], state: Dict[str, Any],
          decision) -> AgentContext:
    """构造 AgentContext（按意图裁剪：knowledge/recommend 不加载订单状态）。"""
    intent = decision.intent if decision else "unknown"
    if intent in ("knowledge", "recommend", "chitchat"):
        state = {}
    ctx = AgentContext(
        user_id=auth.user_id,
        session_id=session_id,
        message=message,
        turn_index=turn_index,
        system_prompt=build_system_prompt(),
        user_profile=profile,
        compressed_summary=summary,
        recent_messages=recent,
        structured_state=state or {},
        route_decision=decision.model_dump() if hasattr(decision, "model_dump") else decision,
        is_minor=auth.is_minor,
        trace_id=f"{session_id}:{turn_index}",
    )
    return ctx


def memory_context_lines(ctx: AgentContext) -> List[str]:
    """把画像/摘要/结构化状态/近期对话拼成文本行。

    供「非 ReAct」的 LLM 回复提示词（naturalize / chitchat / clarify）复用，
    避免这些路径只看到当前输入、丢上下文。ReAct 的 _build_messages 用 role 化消息，
    语义等价但格式不同，故此处独立提供文本行版本。
    """
    lines: List[str] = []
    if ctx.user_profile:
        lines.append("用户画像：" + json.dumps(ctx.user_profile, ensure_ascii=False, default=str))
    if ctx.compressed_summary:
        lines.append("历史摘要：" + ctx.compressed_summary)
    if ctx.structured_state:
        lines.append("结构化状态：" + json.dumps(ctx.structured_state, ensure_ascii=False, default=str))
    history = [f"{'用户' if m.get('role') == 'user' else '助手'}：{m.get('content', '')}"
               for m in ctx.recent_messages
               if m.get('role') in ('user', 'assistant') and m.get('content')]
    if history:
        lines.append("对话历史（最近几轮，供记忆/复述使用）：\n" + "\n".join(history))
    return lines


def assemble_messages(ctx: AgentContext, tool_results: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """按优先级组装最终 messages（供 LLM 层/专家需要时使用）。"""
    messages: List[Dict[str, Any]] = [{"role": "system", "content": ctx.system_prompt}]
    if ctx.user_profile:
        messages.append({"role": "system", "content": f"用户画像：{ctx.user_profile}"})
    if ctx.compressed_summary:
        messages.append({"role": "system", "content": f"历史摘要：{ctx.compressed_summary}"})
    for m in ctx.recent_messages:
        messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    messages.append({"role": "user", "content": ctx.message})
    for tr in (tool_results or ctx.tool_results):
        content = tr.get("content") or tr
        messages.append({"role": "user", "content": f"工具结果：{content}"})
    return messages
