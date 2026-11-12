"""工具错误类型与 ToolResult 三态定义。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ToolResult(BaseModel):
    status: Literal["success", "empty", "error"]
    data: Optional[dict] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class ToolError(Exception):
    pass


class EmptyResult(Exception):
    pass


class TransientError(ToolError):
    pass


def success(data: dict) -> ToolResult:
    return ToolResult(status="success", data=data)


def empty(data: Optional[dict] = None) -> ToolResult:
    return ToolResult(status="empty", data=data)


def error(code: str, message: str = "") -> ToolResult:
    return ToolResult(status="error", error_code=code, error_message=message)


def guard(fn):
    """包裹工具：捕获异常为 error，绝不向 Agent 抛未捕获异常。"""
    async def wrapper(ctx, **kwargs):
        try:
            return await fn(ctx, **kwargs)
        except EmptyResult:
            return empty()
        except ToolError as e:
            return error(getattr(e, "error_code", "tool_error"), str(e))
        except Exception as e:  # noqa: BLE001
            return error("internal_error", str(e))
    wrapper.__name__ = fn.__name__
    return wrapper
