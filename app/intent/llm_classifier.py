"""LLM 层：经 Anthropic SDK 调 DeepSeek，function calling 强制输出结构化结果。

无 API Key 时走确定性 mock 启发式，保证离线可运行。
"""
from __future__ import annotations

import re
from typing import List, Optional

from app.intent import rules
from app.intent.route_decision import RouteDecision
from app.llm.client import complete, extract_json, is_llm_available

_INTENTS = ["recommend", "order", "complaint", "knowledge", "chitchat", "human"]


async def classify(message: str, recent_messages: Optional[List[dict]] = None,
                   compressed_summary: str = "") -> RouteDecision:
    if is_llm_available():
        result = await _llm_classify(message, recent_messages, compressed_summary)
        if result is not None:
            return result
    return _mock_classify(message)


async def _llm_classify(message, recent_messages, compressed_summary) -> Optional[RouteDecision]:
    from app.intent.prompts_loader import load_classify_prompt  # 延迟避免循环

    prompt = load_classify_prompt()
    history = []
    for m in (recent_messages or [])[-3:]:
        if m.get("role") == "user":
            history.append({"role": "user", "content": m.get("content", "")})
        elif m.get("role") == "assistant":
            history.append({"role": "assistant", "content": m.get("content", "")[:100]})
    messages = [{"role": "system", "content": prompt}]
    if compressed_summary:
        messages.append({"role": "system", "content": f"历史摘要：{compressed_summary[:300]}"})
    messages.extend(history)
    messages.append({"role": "user", "content":
        f"当前输入：{message}\n\n"
        f"请只输出一个 JSON 对象，不要输出任何解释或多余文本，格式："
        f'{{"intent": "recommend|order|complaint|knowledge|chitchat|human", '
        f'"confidence": 0.0~1.0 的小数, "reason": "一句话理由"}}'})

    resp = await complete(messages, max_tokens=256, temperature=0.0)
    data = extract_json(resp.get("content"))
    if not data:
        return None
    intent = data.get("intent")
    if intent not in _INTENTS:
        return None
    try:
        conf = float(data.get("confidence", 0.0))
    except (ValueError, TypeError):
        conf = 0.0
    return RouteDecision(intent=intent, confidence=conf,
                         reason=data.get("reason", "llm"), route_source="llm")


def _mock_classify(message: str) -> RouteDecision:
    t = message.strip()
    # 用规则层的否定感知 _has 做关键词匹配（否则"不用推荐/不投诉"会被裸 re.search 误判）
    if rules._has(t, "投诉", "举报", "退款", "太差", "恶心", "欺骗", "态度", "差评"):
        return RouteDecision(intent="complaint", confidence=0.85, reason="mock_keyword", route_source="llm")
    if rules._has(t, "人工", "客服", "真人"):
        return RouteDecision(intent="human", confidence=0.85, reason="mock_keyword", route_source="llm")
    if re.fullmatch(r"\d{8,20}", t):
        return RouteDecision(intent="order", confidence=0.9, reason="mock_order_number", route_source="llm")
    if rules._has(t, "订单") and rules._has(t, "查", "退", "取消", "状态", "改", "催"):
        return RouteDecision(intent="order", confidence=0.8, reason="mock_keyword", route_source="llm")
    if rules._has(t, "多少钱", "怎么收费", "收费", "规则", "包含什么", "能不能", "可以吗", "价格"):
        return RouteDecision(intent="knowledge", confidence=0.7, reason="mock_keyword", route_source="llm")
    if rules._has(t, "推荐", "找个", "有没有", "陪玩", "带飞", "段位", "价位", "性格", "温柔", "技术"):
        return RouteDecision(intent="recommend", confidence=0.7, reason="mock_keyword", route_source="llm")
    return RouteDecision(intent="chitchat", confidence=0.6, reason="mock_default", route_source="llm")
