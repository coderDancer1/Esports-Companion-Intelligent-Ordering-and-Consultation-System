"""Redis 客户端封装。

配置 REDIS_URL 时使用真实 Redis（需安装 redis 包）；否则使用进程内内存实现，
接口与常用 redis 命令保持一致（返回 str，编码为 UTF-8）。
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from app.config import get_settings


class RedisLike:
    """统一的 Redis 兼容接口（字符串编解码为 UTF-8）。"""

    def rpush(self, key: str, *values: str) -> int:  # pragma: no cover
        raise NotImplementedError

    def lrange(self, key: str, start: int, end: int) -> List[str]:  # pragma: no cover
        raise NotImplementedError

    def llen(self, key: str) -> int:  # pragma: no cover
        raise NotImplementedError

    def delete(self, *keys: str) -> int:  # pragma: no cover
        raise NotImplementedError

    def hset(self, key: str, mapping: Dict[str, str]) -> int:  # pragma: no cover
        raise NotImplementedError

    def hget(self, key: str, field: str) -> Optional[str]:  # pragma: no cover
        raise NotImplementedError

    def hgetall(self, key: str) -> Dict[str, str]:  # pragma: no cover
        raise NotImplementedError

    def set(self, key: str, value: str, ex: Optional[int] = None, nx: bool = False,
            px: Optional[int] = None) -> bool:  # pragma: no cover
        raise NotImplementedError

    def get(self, key: str) -> Optional[str]:  # pragma: no cover
        raise NotImplementedError

    def expire(self, key: str, ttl: int) -> bool:  # pragma: no cover
        raise NotImplementedError

    def exists(self, key: str) -> bool:  # pragma: no cover
        raise NotImplementedError

    def release_if_match(self, key: str, value: str) -> bool:  # pragma: no cover
        raise NotImplementedError


class MemoryRedis(RedisLike):
    """进程内内存实现，带简单 TTL 过期。"""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._expire: Dict[str, float] = {}
        self._lock = threading.RLock()

    def _alive(self, key: str) -> bool:
        exp = self._expire.get(key)
        if exp is not None and time.time() > exp:
            self._data.pop(key, None)
            self._expire.pop(key, None)
            return False
        return True

    def rpush(self, key: str, *values: str) -> int:
        with self._lock:
            self._alive(key)
            lst = self._data.setdefault(key, [])
            lst.extend(values)
            return len(lst)

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        with self._lock:
            if not self._alive(key):
                return []
            lst = self._data.get(key, [])
            return list(lst[start:end if end >= 0 else None])

    def llen(self, key: str) -> int:
        with self._lock:
            if not self._alive(key):
                return 0
            return len(self._data.get(key, []))

    def delete(self, *keys: str) -> int:
        with self._lock:
            n = 0
            for k in keys:
                if k in self._data:
                    self._data.pop(k, None)
                    self._expire.pop(k, None)
                    n += 1
            return n

    def hset(self, key: str, mapping: Dict[str, str]) -> int:
        with self._lock:
            self._alive(key)
            h = self._data.setdefault(key, {})
            added = 0
            for k, v in mapping.items():
                if k not in h:
                    added += 1
                h[k] = str(v)
            return added

    def hget(self, key: str, field: str) -> Optional[str]:
        with self._lock:
            if not self._alive(key):
                return None
            v = self._data.get(key, {}).get(field)
            return v if v is None else str(v)

    def hgetall(self, key: str) -> Dict[str, str]:
        with self._lock:
            if not self._alive(key):
                return {}
            return {str(k): str(v) for k, v in self._data.get(key, {}).items()}

    def set(self, key: str, value: str, ex: Optional[int] = None, nx: bool = False,
            px: Optional[int] = None) -> bool:
        with self._lock:
            if nx and self._alive(key) and key in self._data:
                return False
            self._data[key] = str(value)
            if px is not None:
                self._expire[key] = time.time() + px / 1000.0
            elif ex is not None:
                self._expire[key] = time.time() + ex
            return True

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if not self._alive(key):
                return None
            v = self._data.get(key)
            return None if v is None else str(v)

    def expire(self, key: str, ttl: int) -> bool:
        with self._lock:
            if key in self._data:
                self._expire[key] = time.time() + ttl
                return True
            return False

    def exists(self, key: str) -> bool:
        with self._lock:
            return self._alive(key) and key in self._data

    def release_if_match(self, key: str, value: str) -> bool:
        with self._lock:
            if self._data.get(key) == str(value):
                self._data.pop(key, None)
                self._expire.pop(key, None)
                return True
            return False


class RealRedis(RedisLike):
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)

    def rpush(self, key, *values):
        return self._r.rpush(key, *values)

    def lrange(self, key, start, end):
        return self._r.lrange(key, start, end)

    def llen(self, key):
        return self._r.llen(key)

    def delete(self, *keys):
        return self._r.delete(*keys)

    def hset(self, key, mapping):
        return self._r.hset(key, mapping=mapping)

    def hget(self, key, field):
        return self._r.hget(key, field)

    def hgetall(self, key):
        return self._r.hgetall(key)

    def set(self, key, value, ex=None, nx=False, px=None):
        return self._r.set(key, value, ex=ex, nx=nx, px=px)

    def get(self, key):
        return self._r.get(key)

    def expire(self, key, ttl):
        return self._r.expire(key, ttl)

    def exists(self, key):
        return bool(self._r.exists(key))

    def release_if_match(self, key, value):
        lua = ("if redis.call('get', KEYS[1]) == ARGV[1] then "
               "return redis.call('del', KEYS[1]) else return 0 end")
        return bool(self._r.eval(lua, 1, key, value))


_client: Optional[RedisLike] = None


def get_redis() -> RedisLike:
    global _client
    if _client is None:
        url = get_settings().REDIS_URL
        if url and url != "mock":
            try:
                _client = RealRedis(url)
            except Exception:
                _client = MemoryRedis()
        else:
            _client = MemoryRedis()
    return _client


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def json_loads(text: Optional[str]) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None
