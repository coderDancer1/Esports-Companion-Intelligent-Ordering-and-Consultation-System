"""Bearer token 解析，产出 AuthUser；失败抛 401。

JWT 采用 HS256（纯标准库实现，无需额外依赖）。
另提供开发模式：`Bearer demo_<user_id>` 直接映射到对应用户，便于本地联调。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import get_settings


class AuthUser(BaseModel):
    user_id: str
    is_minor: bool
    token_exp: int


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _sign(data: bytes) -> str:
    s = get_settings()
    mac = hmac.new(s.JWT_SECRET.encode("utf-8"), data, hashlib.sha256).digest()
    return _b64url_encode(mac)


def mint_token(user_id: str, is_minor: bool = False, ttl_seconds: int = 7 * 86400) -> str:
    """生成 JWT。"""
    now = int(time.time())
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url_encode(json.dumps(
        {"sub": user_id, "is_minor": is_minor, "iat": now, "exp": now + ttl_seconds}
    ).encode("utf-8"))
    signing_input = f"{header}.{payload}"
    return f"{signing_input}.{_sign(signing_input.encode('utf-8'))}"


def _decode_jwt(token: str) -> Optional[dict]:
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}"
        expected = _sign(signing_input.encode("utf-8"))
        if not hmac.compare_digest(expected, signature):
            return None
        return json.loads(_b64url_decode(payload))
    except Exception:  # noqa: BLE001
        return None


_bearer_scheme = HTTPBearer(auto_error=False)


async def get_auth_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthUser:
    """解析 Authorization: Bearer <token>。

    - 合法 JWT：解析 sub/is_minor/exp；
    - 开发模式 demo_<user_id>：映射到该用户；
    - 其余一律 401。
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing_token")
    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="missing_token")

    # 开发模式
    if token.startswith("demo_"):
        user_id = token[len("demo_"):]
        is_minor = _lookup_minor(user_id)
        return AuthUser(user_id=user_id, is_minor=is_minor, token_exp=int(time.time()) + 3600)

    payload = _decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid_token")
    exp = payload.get("exp", 0)
    if exp and int(exp) < int(time.time()):
        raise HTTPException(status_code=401, detail="token_expired")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="invalid_token")
    return AuthUser(user_id=str(sub), is_minor=bool(payload.get("is_minor", False)), token_exp=int(exp))


def _lookup_minor(user_id: str) -> bool:
    """从用户表读取是否未成年（未找到视为 False）。"""
    try:
        from app.db.mysql import session_scope
        from app.db.models import User

        with session_scope() as db:
            user = db.get(User, user_id)
            return bool(user.is_minor) if user else False
    except Exception:  # noqa: BLE001
        return False
