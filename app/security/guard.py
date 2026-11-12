"""安全护栏：user_id 一致性校验、未成年人拦截。"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from app.security.auth import AuthUser


async def ensure_user_id_match(auth: AuthUser, body_user_id: Optional[str]) -> None:
    """body.user_id 可缺省；若提供且与 token 不一致 → 403。

    业务逻辑一律使用 auth.user_id，绝不使用 body.user_id。
    """
    if body_user_id is not None and body_user_id != auth.user_id:
        raise HTTPException(status_code=403, detail="user_id_mismatch")


async def ensure_not_minor(auth: AuthUser) -> None:
    """涉及下单/充值/打赏前调用；未成年人拦截。"""
    if auth.is_minor:
        raise HTTPException(status_code=403, detail="minor_restricted")
