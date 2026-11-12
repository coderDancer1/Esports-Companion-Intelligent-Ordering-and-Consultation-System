"""LLM 调用封装。

统一经 Anthropic SDK 调用 DeepSeek 兼容端点（base_url 指向 api.deepseek.com/anthropic）。
无 API Key 时 is_llm_available() 返回 False，各消费者走确定性 mock 降级，
保证系统脱离外部服务仍可端到端运行。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.config import get_settings

_client = None


def is_llm_available() -> bool:
    return bool(get_settings().DEEPSEEK_API_KEY)


def get_client():
    global _client
    if _client is None and is_llm_available():
        from anthropic import AsyncAnthropic

        s = get_settings()
        _client = AsyncAnthropic(api_key=s.DEEPSEEK_API_KEY, base_url=s.DEEPSEEK_ANTHROPIC_BASE_URL)
    return _client


async def complete(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Dict[str, Any]] = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """调用 LLM，返回归一化结构 {content, tool_calls, raw}。

    tool_calls: [{name, input}]；content: 纯文本回复（可为 None）。
    失败自动重试一次，超时兜底。
    """
    if not is_llm_available():
        return {"content": None, "tool_calls": [], "mock": True}

    client = get_client()
    s = get_settings()
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            kwargs: Dict[str, Any] = {
                "model": s.DEEPSEEK_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            # 思考模式模型：关闭 thinking 以直接拿到 text 块（否则 thinking 会耗尽 token）
            if getattr(s, "DEEPSEEK_THINKING", ""):
                kwargs["thinking"] = {"type": s.DEEPSEEK_THINKING}
            if tools:
                kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
            resp = await asyncio.wait_for(client.messages.create(**kwargs), timeout=30.0)
            content_parts: List[str] = []
            tool_calls: List[Dict[str, Any]] = []
            for block in resp.content:
                if getattr(block, "type", None) == "text":
                    content_parts.append(block.text)
                elif getattr(block, "type", None) == "tool_use":
                    tool_calls.append({"name": block.name, "input": dict(block.input or {})})
            return {"content": "".join(content_parts) or None, "tool_calls": tool_calls, "raw": resp}
        except Exception as e:  # noqa: BLE001
            last_err = e
            await asyncio.sleep(0.2)
    return {"content": None, "tool_calls": [], "error": str(last_err)}


def extract_json(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """从 LLM 文本回复中稳健抽取首个 JSON 对象（兼容思考模型直接输出 JSON）。"""
    import json
    import re

    if not text:
        return None
    s = text.strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
