"""FastAPI 依赖注入工厂。

提供 db session、redis、chroma、auth 的 Depends 工厂。
in-process 工具层直接使用 db/mysql.session_scope、db/redis_client.get_redis 等，
不经过此处的 FastAPI 依赖。
"""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends

from app.db.mysql import session_scope
from app.security.auth import AuthUser, get_auth_user


def get_db():
    """HTTP 接口使用的会话依赖。"""
    with session_scope() as db:
        yield db


def get_redis_client():
    from app.db.redis_client import get_redis

    return get_redis()


def get_chroma_client():
    from app.db.chroma_client import get_chroma

    return get_chroma()


def get_current_user(auth: AuthUser = Depends(get_auth_user)) -> AuthUser:
    return auth
