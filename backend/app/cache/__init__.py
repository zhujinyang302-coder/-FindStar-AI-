"""缓存能力包。

Redis 兼容服务优先；连接失败或未配置时自动降级为进程内内存缓存。
缓存仅用于加速，业务数据始终以数据库为唯一事实来源。
"""

from app.cache.redis_cache import CacheManager, cache_manager, get_cache

__all__ = ["CacheManager", "cache_manager", "get_cache"]