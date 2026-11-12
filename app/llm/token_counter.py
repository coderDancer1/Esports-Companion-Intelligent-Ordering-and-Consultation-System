"""token 估算。

优先尝试 Anthropic count_tokens；端点不支持时退化为字符数/1.7 的粗略估算，
误差由 70% 压缩触发线预留的余量吸收。估算不追求精确，不阻塞实现。
"""
from __future__ import annotations

from typing import Any, Dict, List, Union

from app.llm.client import get_client


def _chars(text: Any) -> int:
    if text is None:
        return 0
    return len(str(text))


def estimate_text(text: str) -> int:
    return max(1, int(_chars(text) / 1.7))


def estimate_messages(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += estimate_text(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += estimate_text(part.get("text", ""))
        total += 4  # 每条消息的固定开销
    return max(1, total)


def estimate(text_or_messages: Union[str, List[Dict[str, Any]]]) -> int:
    """统一入口：字符串或消息列表均可。"""
    if isinstance(text_or_messages, str):
        return estimate_text(text_or_messages)
    if isinstance(text_or_messages, list):
        return estimate_messages(text_or_messages)
    return estimate_text(str(text_or_messages))


async def count_tokens(text_or_messages: Union[str, List[Dict[str, Any]]]) -> int:
    """优先走 SDK count_tokens，失败降级为字符估算。"""
    client = get_client()
    if client is not None:
        try:
            if isinstance(text_or_messages, str):
                resp = client.messages.count_tokens(
                    model=get_client_model(), messages=[{"role": "user", "content": text_or_messages}]
                )
            else:
                resp = client.messages.count_tokens(model=get_client_model(), messages=text_or_messages)
            return int(resp.input_tokens)
        except Exception:  # noqa: BLE001
            pass
    return estimate(text_or_messages)


def get_client_model() -> str:
    from app.config import get_settings

    return get_settings().DEEPSEEK_MODEL
