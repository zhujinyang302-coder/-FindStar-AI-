"""缓存封装：Redis 优先，内存降级。

缓存键规范：
- 热点列表：findstar:items:latest:{page}:{filter_hash}
- 匹配结果：findstar:match:{record_type}:{record_id}:{algorithm_version}:{data_version}
- 接口限流：findstar:rate:{user_id}:{route}
- 幂等请求：findstar:idempotency:{user_id}:{key}

记录更新/下架/状态变化时必须清理相关缓存前缀。
缓存不可用时不影响核心数据；禁止将唯一业务数据只保存在缓存中。
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "findstar"


class _MemoryBackend:
    """进程内缓存（降级用），带 TTL 与线程安全。"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expire_at, value = item
            if expire_at and expire_at < time.time():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl: int | None) -> None:
        expire_at = time.time() + ttl if ttl else 0.0
        with self._lock:
            self._store[key] = (expire_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

    def incr(self, key: str, ttl: int) -> int:
        with self._lock:
            item = self._store.get(key)
            if item is None or (item[0] and item[0] < time.time()):
                self._store[key] = (time.time() + ttl, "1")
                return 1
            count = int(item[1]) + 1
            self._store[key] = (item[0], str(count))
            return count


class CacheManager:
    def __init__(self) -> None:
        self._memory = _MemoryBackend()
        self._redis: Any = None
        self.degraded = True
        self.degraded_reason = "未配置 REDIS_URL 或缓存已关闭"
        self._init_redis()

    def _init_redis(self) -> None:
        if not settings.cache_enabled or not settings.redis_url:
            return
        try:
            import redis  # 延迟导入，避免未安装时影响启动

            client = redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            self.degraded = False
            self.degraded_reason = ""
            logger.info("redis cache connected")
        except Exception as exc:  # noqa: BLE001
            self._redis = None
            self.degraded = True
            self.degraded_reason = f"Redis 不可用，已降级为内存缓存：{type(exc).__name__}"
            logger.warning("redis unavailable, fallback to memory cache")

    def _redis_ok(self) -> bool:
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:  # noqa: BLE001
            self._redis = None
            self.degraded = True
            self.degraded_reason = "Redis 运行中不可用，已降级为内存缓存"
            return False

    # ---- 基础操作 ----
    def get_json(self, key: str) -> Any | None:
        raw = self._get_raw(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            raw = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return
        self._set_raw(key, raw, ttl)

    def _get_raw(self, key: str) -> str | None:
        if self._redis_ok():
            try:
                return self._redis.get(key)
            except Exception:  # noqa: BLE001
                self.degraded = True
        return self._memory.get(key)

    def _set_raw(self, key: str, value: str, ttl: int | None) -> None:
        if self._redis_ok():
            try:
                if ttl:
                    self._redis.setex(key, ttl, value)
                else:
                    self._redis.set(key, value)
                return
            except Exception:  # noqa: BLE001
                self.degraded = True
        self._memory.set(key, value, ttl)

    def delete(self, key: str) -> None:
        if self._redis_ok():
            try:
                self._redis.delete(key)
            except Exception:  # noqa: BLE001
                self.degraded = True
        self._memory.delete(key)

    def delete_prefix(self, prefix: str) -> int:
        removed = 0
        if self._redis_ok():
            try:
                cursor, keys = 0, []
                while True:
                    cursor, batch = self._redis.scan(cursor=cursor, match=f"{prefix}*", count=200)
                    keys.extend(batch)
                    if cursor == 0:
                        break
                if keys:
                    removed = self._redis.delete(*keys)
            except Exception:  # noqa: BLE001
                self.degraded = True
        removed += self._memory.delete_prefix(prefix)
        return removed

    def incr(self, key: str, ttl: int) -> int:
        if self._redis_ok():
            try:
                count = self._redis.incr(key)
                if count == 1:
                    self._redis.expire(key, ttl)
                return int(count)
            except Exception:  # noqa: BLE001
                self.degraded = True
        return self._memory.incr(key, ttl)

    @property
    def available(self) -> bool:
        return not self.degraded

    # ---- 业务缓存键 ----
    def invalidate_items(self) -> int:
        """记录新增/更新/下架/状态变化时清理列表缓存。"""
        return self.delete_prefix(f"{_PREFIX}:items:")

    def invalidate_matches(self) -> int:
        return self.delete_prefix(f"{_PREFIX}:match:")

    def invalidate_all(self) -> int:
        return self.delete_prefix(f"{_PREFIX}:items:") + self.delete_prefix(f"{_PREFIX}:match:")

    @staticmethod
    def items_key(page: int, filter_hash: str) -> str:
        return f"{_PREFIX}:items:latest:{page}:{filter_hash}"

    @staticmethod
    def match_key(record_type: str, record_id: int, algorithm_version: str, data_version: str) -> str:
        return f"{_PREFIX}:match:{record_type}:{record_id}:{algorithm_version}:{data_version}"

    @staticmethod
    def rate_key(user_id: int | str, route: str) -> str:
        return f"{_PREFIX}:rate:{user_id}:{route}"


cache_manager = CacheManager()


def get_cache() -> CacheManager:
    return cache_manager