"""各专家回复提示词：每个 intent 一套角色+规则，组装最终回复生成 prompt。

设计：确定性数据抽取（工具/正则/向量/RAG）保持不变，只把「最终话术」交给 LLM。
每个 intent 有独立的角色定位与输出规则，再叠加该 intent 的结构化事实（facts/cards/ticket 等），
让回复既自然又不会编造。LLM 失败时回退到专家内置的模板回复。
"""
from __future__ import annotations

from typing import Any, Dict

from app.memory.assembler import memory_context_lines

ROLE_PROMPTS: Dict[str, str] = {
    "recommend": (
        "你是陪玩推荐顾问。根据筛选条件与候选结果，用自然、可解释的中文推荐陪玩师。\n"
        "规则：先说明筛选条件，再列出结果，最后给推荐理由；理由结合段位、价位、准时率、标签、评分；"
        "空结果时建议放宽条件（提高预算/放宽段位/去掉标签），不得编造；每次最多展示 3-5 位。"
    ),
    "order": (
        "你是订单售后顾问。你只做「可执行性判断 + 参数说明」，绝不直接修改订单状态或操作资金。\n"
        "规则：如实汇报订单状态、金额、游戏、托管状态；退款/取消/改单只输出可执行性判断与参数，"
        "实际执行由后端完成；查无此单要如实说「没有查到」，查失败说「暂时查不到，可转人工」；"
        "需要人工时明确转人工并携带订单号。"
    ),
    "complaint": (
        "你是投诉处理专员。先安抚用户情绪，再说明处理方式。\n"
        "规则：情绪强烈时先安抚并明确会跟进；命中转人工规则时明确告知已创建工单、客服稍后联系；"
        "不得承诺具体赔付金额或时间。"
    ),
    "knowledge": (
        "你是平台规则咨询助手。只基于检索到的文档作答。\n"
        "规则：优先引用检索到的原文片段，保留金额、规则等关键数字；注明来源（文档标题）；"
        "未找到时明示「没有找到相关说明」并给出转人工入口；不得编造规则。"
    ),
    "clarify": (
        "你在向用户澄清意图。让用户从候选意图中选择一个，用自然友好的话术询问，不要替用户做决定。"
    ),
    "human": (
        "你在安抚用户并告知转人工。明确告知已创建工单、排队位置、客服稍后联系，语气要安抚、稳妥。"
    ),
    "chitchat": (
        "你是电竞陪玩平台的客服助手，正在和用户闲聊。用自然、友好、简洁的中文回应，"
        "可顺势引导用户到推荐陪玩、查订单、咨询平台规则等业务。"
    ),
}

INTENT_LABEL: Dict[str, str] = {
    "recommend": "推荐陪玩", "order": "订单查询/售后", "complaint": "投诉",
    "knowledge": "平台规则咨询", "chitchat": "闲聊", "human": "转人工",
}


def build_reply_prompt(intent: str, ctx: Any, result: Dict[str, Any]) -> str:
    """按意图组装回复生成 prompt：角色规则 + 结构化事实 + 用户输入。"""
    role = ROLE_PROMPTS.get(intent, ROLE_PROMPTS["chitchat"])
    parts = [role]

    facts = [(k, v) for k, v in (result.get("facts") or {}).items() if v not in (None, "")]
    cards = result.get("cards")
    if cards:
        names = "、".join(
            f"{c.get('nickname')}({c.get('rank')},{c.get('price_per_hour')}元)"
            for c in cards[:5]
        )
        facts.append(("候选陪玩", names))
    if result.get("ticket_id"):
        facts.append(("工单号", result["ticket_id"]))
    if result.get("clarify_options"):
        labels = "、".join(INTENT_LABEL.get(o, o) for o in result["clarify_options"])
        facts.append(("候选意图", labels))

    if facts:
        facts_text = "\n".join(f"- {k}：{v}" for k, v in facts)
        parts.append(f"已确定的业务信息（必须如实保留，不得编造）：\n{facts_text}")
    elif intent != "chitchat" and result.get("reply"):
        # 没有结构化事实时，才把模板回复作为参考（避免话术被模板带偏）
        parts.append(f"系统参考回复：{result['reply']}")

    # 多轮记忆：把画像/摘要/结构化状态/近期对话注入提示词，使 LLM 能记忆与复述上下文
    memory_lines = memory_context_lines(ctx)
    if memory_lines:
        parts.append("\n".join(memory_lines))

    parts.append(f"用户当前输入：{ctx.message}")
    parts.append("请直接输出给用户的一句或一段中文回复，自然友好、简洁，"
                 "不要输出任何解释、前缀或 Markdown 标记。")
    return "\n".join(parts)
