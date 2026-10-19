from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_client: Redis | None = None
_state = "unconfigured"
_memory_buckets: dict[str, tuple[int, int]] = {}


def redis_state() -> str:
    return _state


def init_redis(url: str) -> None:
    global _client, _state
    cleaned = (url or "").strip()
    if not cleaned or cleaned.lower() in {"disabled", "none", "off"}:
        _client = None
        _state = "unconfigured"
        logger.info("redis disabled; rate limiting and caching run in-process")
        return
    try:
        client = Redis.from_url(cleaned, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
        client.ping()
    except Exception:
        logger.warning("redis unavailable; continuing in degraded mode", exc_info=True)
        _client = None
        _state = "degraded"
        return
    _client = client
    _state = "ok"
    logger.info("redis connected")


def mark_redis_down() -> None:
    global _client, _state
    _client = None
    _state = "degraded"


def get_redis() -> Redis | None:
    return _client


def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            logger.warning("error closing redis", exc_info=True)
    _client = None


def allow(key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
    """Return (allowed, remaining). Limit <= 0 disables the limiter."""
    if limit <= 0:
        return True, 0
    client = get_redis()
    if client is not None:
        try:
            return _allow_redis(client, key, limit, window_seconds)
        except RedisError:
            logger.warning("redis rate limit failed; using in-process limiter", exc_info=True)
            mark_redis_down()
    return _allow_memory(key, limit, window_seconds)


def _allow_redis(client: Redis, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    redis_key = f"rl:{key}"
    count = int(client.incr(redis_key))
    if count == 1:
        client.expire(redis_key, window_seconds)
    if count > limit:
        return False, 0
    return True, limit - count


def _allow_memory(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    slot = int(time.time() // window_seconds)
    bucket = f"{key}:{slot}"
    with _lock:
        if len(_memory_buckets) > 20_000:
            _memory_buckets.clear()
        count, _stored_slot = _memory_buckets.get(bucket, (0, slot))
        count += 1
        _memory_buckets[bucket] = (count, slot)
    if count > limit:
        return False, 0
    return True, limit - count


def reset_memory_limiter() -> None:
    with _lock:
        _memory_buckets.clear()


def cache_get(key: str) -> Any | None:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except RedisError:
        logger.warning("redis cache read failed", exc_info=True)
        mark_redis_down()
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 15) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except RedisError:
        logger.warning("redis cache write failed", exc_info=True)
        mark_redis_down()


def acquire_lock(name: str, ttl_seconds: int) -> bool:
    """Best-effort lock. When Redis is down, allow the caller to proceed."""
    client = get_redis()
    if client is None:
        return True
    try:
        return bool(client.set(f"lock:{name}", "1", nx=True, ex=ttl_seconds))
    except RedisError:
        logger.warning("redis lock failed", exc_info=True)
        mark_redis_down()
        return True
