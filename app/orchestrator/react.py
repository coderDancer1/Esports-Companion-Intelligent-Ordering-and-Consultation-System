"""ReAct 工具调用回路。

核心是一个可复用的 async generator `react_events(ctx, intent)`：
  - 逐 step 用 LLM（携带该意图的常驻工具 schema）观察→规划→调用工具→观察结果→迭代；
  - 每一步流式产出文本增量事件 {'type': 'delta', 'text': ...}（供 SSE 转发）；
  - 拿到最终答复后产出 {'type': 'done', 'result': {...}}。

`result` 内除 `reply/cards/ticket_id/handoff_to_human/tool_calls` 外，还带完整
`steps` 轨迹（每步的 thought + 每次工具调用的 params/status/result 摘要），
供 `/chat` 响应与 `/admin/logs` 做可观测性追踪。

仅当 is_llm_available() 时生效；否则不产出 done，交由确定性专家回退。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.llm.client import get_client, is_llm_available
from app.memory.assembler import BASE_SYSTEM
from app.orchestrator.experts.base import log_tool
from app.tools.errors import error as tool_error
from app.tools.registry import get_resident_schemas, get_tool
from app.skills.loader import catalog_text

# 各意图的 ReAct 角色引导（区别于 expert_prompts 的"最终话术"提示词）
_ROLE_GUIDANCE = {
    "recommend": "你是推荐专家。先调用 search_playmates 检索候选（把用户原话作为 semantic_query 传入），"
                 "必要时 get_playmate_detail 查看详情；基于返回数据推荐，并如实说明匹配理由。",
    "order": "你是订单专家。先 query_order 查订单；涉及退款/取消/改单/改期时调用 check_action_eligibility "
             "判断是否可执行（只判断、绝不执行写操作）。",
    "complaint": "你是售后专家。先 assess_emotion 评估情绪，再 check_handoff_rules 判断是否需转人工；"
                 "命中转人工规则时调用 create_handoff_ticket 建单并告知排队信息。",
    "knowledge": "你是知识问答专家。调用 search_knowledge_base 检索说明，严格基于检索结果作答；"
                 "检索为空时如实说明，不得编造。",
    "human": "你是转人工专家。调用 create_handoff_ticket 建单并告知排队信息。",
    "clarify": "你是澄清专家。基于上下文追问用户需求，必要时调用 get_user_profile 了解画像。",
    "chitchat": "你是闲聊助手。简短友好地回应，无需调用工具。",
}

# LLM 观察用的工具结果上限 / trace 摘要上限（防止大结果撑爆上下文）
_OBSERVE_MAX_CHARS = 2000
_TRACE_MAX_CHARS = 300


def _system_prompt(intent: str) -> str:
    return (BASE_SYSTEM + "\n" + _ROLE_GUIDANCE.get(intent, "")
            + "\n\n可用技能（需要时调用 load_skill 加载正文，不要一次性全部加载）：\n"
            + catalog_text())


def _tool_result_content(res, max_chars: int = _OBSERVE_MAX_CHARS) -> str:
    """ToolResult → 交给 LLM 观察的 JSON 文本（截断）。"""
    try:
        data = res.model_dump()
    except Exception:  # noqa: BLE001
        data = {"status": "error", "error_message": str(res)}
    s = json.dumps(data, ensure_ascii=False, default=str)
    if len(s) > max_chars:
        s = s[:max_chars] + f"...（已截断，原长 {len(s)}）"
    return s


def _data_digest(res, max_chars: int = _TRACE_MAX_CHARS) -> str:
    """trace 用的一行式结果摘要：error 给错误码，否则给 data 片段。"""
    status = getattr(res, "status", "error")
    if status == "error":
        code = getattr(res, "error_code", "") or "error"
        msg = getattr(res, "error_message", "") or ""
        return f"{code}: {msg}"[:max_chars]
    s = json.dumps(getattr(res, "data", None), ensure_ascii=False, default=str)
    if len(s) > max_chars:
        s = s[:max_chars] + "…"
    return s


async def _execute(ctx, name: str, inputs: Dict[str, Any]):
    """执行单个工具并返回 ToolResult；一切异常兜底为 error，绝不向回路抛出。"""
    tool_def = get_tool(name)
    if not tool_def:
        return tool_error("unknown_tool", f"未注册工具 {name}")
    digest = json.dumps(inputs, ensure_ascii=False, default=str)[:200]
    try:
        res = await tool_def["run"](ctx, **inputs)
    except TypeError as e:
        log_tool(ctx, name, digest, "bad_input")
        return tool_error("bad_tool_input", str(e))
    except Exception as e:  # noqa: BLE001
        log_tool(ctx, name, digest, "error")
        return tool_error("tool_exec_failed", str(e))
    log_tool(ctx, name, digest, getattr(res, "status", "unknown"))
    return res


def _block_to_dict(block) -> Dict[str, Any]:
    if getattr(block, "type", None) == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    return {"type": "tool_use", "id": getattr(block, "id", ""),
            "name": getattr(block, "name", ""), "input": dict(getattr(block, "input", None) or {})}


def _reason(it: Dict[str, Any]) -> str:
    tags = "、".join(it.get("personality_tags") or []) or "综合"
    ontime = int(round((it.get("ontime_rate") or 0) * 100))
    return (f"{it.get('rank')}段位，{tags}，近30天准时率{ontime}%，"
            f"价位{it.get('price_per_hour')}元/时")


def _card(it: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "playmate", "id": it["id"], "nickname": it["nickname"],
            "game": it["game"], "rank": it["rank"], "price_per_hour": it["price_per_hour"],
            "personality_tags": it["personality_tags"], "match_score": it.get("match_score"),
            "reason": _reason(it)}


def _build_messages(ctx, intent: str) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = [{"role": "system", "content": _system_prompt(intent)}]
    if ctx.user_profile:
        messages.append({"role": "system", "content":
                         "用户画像：" + json.dumps(ctx.user_profile, ensure_ascii=False, default=str)})
    if ctx.compressed_summary:
        messages.append({"role": "system", "content": f"历史摘要：{ctx.compressed_summary}"})
    if ctx.structured_state:
        messages.append({"role": "system", "content":
                         "结构化状态：" + json.dumps(ctx.structured_state, ensure_ascii=False, default=str)})
    for m in ctx.recent_messages:
        role = m.get("role")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": ctx.message})
    return messages


def _materialize(reply: str, steps: List[Dict[str, Any]], cards_data: List[Dict[str, Any]],
                 ticket_id: Optional[str], handoff: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {"reply": reply, "handoff_to_human": handoff}
    out["steps"] = steps
    out["tool_calls"] = [{"name": tc["tool"], "status": tc["status"]}
                         for s in steps for tc in s.get("tool_calls", [])]
    out["llm_generated"] = True
    if cards_data:
        cards = []
        for it in cards_data:
            try:
                cards.append(_card(it))
            except Exception:  # noqa: BLE001
                continue
        if cards:
            out["cards"] = cards
    if ticket_id:
        out["ticket_id"] = ticket_id
    return out


async def react_events(ctx, intent: str):
    """ReAct 核心生成器：yield {'type':'delta'|'done', ...}。失败时不产出 done。"""
    if not is_llm_available():
        return
    schemas = get_resident_schemas(intent)
    if not schemas:
        return

    client = get_client()
    s = get_settings()
    max_steps = getattr(s, "REACT_MAX_STEPS", 4)

    messages = _build_messages(ctx, intent)
    steps: List[Dict[str, Any]] = []
    cards_data: List[Dict[str, Any]] = []
    ticket_id: Optional[str] = None
    handoff = False

    for step_idx in range(max_steps):
        kwargs: Dict[str, Any] = {
            "model": s.DEEPSEEK_MODEL,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.2,
            "tools": schemas,
        }
        if getattr(s, "DEEPSEEK_THINKING", ""):
            kwargs["thinking"] = {"type": s.DEEPSEEK_THINKING}

        text_parts: List[str] = []
        try:
            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    text_parts.append(text)
                    yield {"type": "delta", "text": text}
                final = await stream.get_final_message()
        except Exception:  # noqa: BLE001
            break

        tool_blocks = [b for b in final.content if getattr(b, "type", None) == "tool_use"]
        if not tool_blocks:
            reply = "".join(text_parts).strip()
            if reply:
                yield {"type": "done",
                       "result": _materialize(reply, steps, cards_data, ticket_id, handoff)}
            return

        # 该步在工具调用前产出的文本 → 记为 thought（LLM 的"计划/想法"）
        thought = "".join(text_parts).strip()

        # 追加 assistant（含 tool_use 块）
        messages.append({"role": "assistant", "content": [_block_to_dict(b) for b in final.content]})

        step_tool_calls: List[Dict[str, Any]] = []
        result_blocks: List[Dict[str, Any]] = []
        for b in tool_blocks:
            name = getattr(b, "name", "")
            inputs = dict(getattr(b, "input", None) or {})
            res = await _execute(ctx, name, inputs)
            d = getattr(res, "data", None) or {}
            status = getattr(res, "status", "error")
            step_tool_calls.append({"tool": name, "params": inputs, "status": status,
                                    "result": _data_digest(res)})
            result_blocks.append({"type": "tool_result", "tool_use_id": getattr(b, "id", ""),
                                  "content": _tool_result_content(res)})
            # 物化关键结果
            if name == "search_playmates" and status == "success":
                cards_data.extend(d.get("items") or [])
            if name == "create_handoff_ticket" and status == "success":
                ticket_id = d.get("ticket_id")
                handoff = True
            if name == "check_handoff_rules" and status == "success" and d.get("should_handoff"):
                handoff = True
        steps.append({"step": step_idx + 1, "thought": thought, "tool_calls": step_tool_calls})
        messages.append({"role": "user", "content": result_blocks})

    # 达到最大步数仍未收尾 → 视为失败（交给回退）