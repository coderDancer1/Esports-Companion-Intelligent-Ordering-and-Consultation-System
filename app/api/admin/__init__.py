"""管理端接口（X-Admin-Key 鉴权）。"""
from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import get_settings


async def require_admin(x_admin_key: str = Header(default="")):
    if x_admin_key != get_settings().ADMIN_KEY:
        raise HTTPException(status_code=403, detail="invalid_admin_key")
