"""Redis 分布式锁：SET NX PX 加锁，释放时比对 value（Lua / 原子比较删除）。"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from app.db.redis_client import get_redis


class RedisLock:
    def __init__(self, key: str, ttl: int = 60) -> None:
        self.key = key
        self.ttl = ttl
        self.token = secrets.token_hex(16)
        self._acquired = False

    async def acquire(self) -> bool:
        r = get_redis()
        self._acquired = bool(r.set(self.key, self.token, nx=True, px=self.ttl * 1000))
        return self._acquired

    async def release(self) -> None:
        if not self._acquired:
            return
        get_redis().release_if_match(self.key, self.token)
        self._acquired = False

    def __enter__(self):  # pragma: no cover - 同步便捷用法
        r = get_redis()
        self._acquired = bool(r.set(self.key, self.token, nx=True, px=self.ttl * 1000))
        if not self._acquired:
            raise RuntimeError("lock not acquired")
        return self

    def __exit__(self, *exc):  # pragma: no cover
        self.release_sync()

    def release_sync(self):  # pragma: no cover
        if self._acquired:
            get_redis().release_if_match(self.key, self.token)
            self._acquired = False


def now_ts() -> int:
    return int(time.time())
