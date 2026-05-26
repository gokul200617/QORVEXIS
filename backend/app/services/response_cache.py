"""In-memory response cache — lightweight LRU cache with configurable TTL."""

import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic

from app.settings import settings

logger = logging.getLogger("qorvexis.cache")


@dataclass
class CacheEntry:
    response: str
    provider: str
    model: str
    created_at: float
    ttl: int


class ResponseCache:
    """Thread-safe, in-memory LRU response cache.

    Keys are SHA-256 hashes of normalized prompts.
    Entries expire after ``settings.cache_ttl_seconds``.
    Max entries limited by ``settings.cache_max_entries``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_lookups = 0

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        return " ".join(prompt.lower().split())

    @staticmethod
    def _hash_prompt(normalized: str) -> str:
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, prompt: str) -> CacheEntry | None:
        key = self._hash_prompt(self._normalize_prompt(prompt))
        with self._lock:
            self._total_lookups += 1
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            if (monotonic() - entry.created_at) > entry.ttl:
                del self._store[key]
                self._misses += 1
                logger.info("cache.expired key=%s", key[:12])
                return None

            self._store.move_to_end(key)
            self._hits += 1
            logger.info("cache.hit key=%s provider=%s", key[:12], entry.provider)
            return entry

    def put(self, prompt: str, response: str, provider: str, model: str) -> None:
        normalized = self._normalize_prompt(prompt)
        key = self._hash_prompt(normalized)
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = CacheEntry(
                    response=response,
                    provider=provider,
                    model=model,
                    created_at=monotonic(),
                    ttl=settings.cache_ttl_seconds,
                )
                return

            self._store[key] = CacheEntry(
                response=response,
                provider=provider,
                model=model,
                created_at=monotonic(),
                ttl=settings.cache_ttl_seconds,
            )

            while len(self._store) > settings.cache_max_entries:
                evicted_key, _entry = self._store.popitem(last=False)
                self._evictions += 1
                logger.info("cache.eviction key=%s", evicted_key[:12])

        logger.info("cache.put key=%s provider=%s", key[:12], provider)

    def invalidate(self, prompt: str) -> bool:
        key = self._hash_prompt(self._normalize_prompt(prompt))
        with self._lock:
            if key in self._store:
                del self._store[key]
                logger.info("cache.invalidate key=%s", key[:12])
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
        logger.info("cache.clear")

    def snapshot(self) -> dict:
        with self._lock:
            hit_ratio = (
                round((self._hits / self._total_lookups) * 100, 2)
                if self._total_lookups
                else 0
            )
            return {
                "entries": len(self._store),
                "max_entries": settings.cache_max_entries,
                "ttl_seconds": settings.cache_ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "total_lookups": self._total_lookups,
                "hit_ratio": hit_ratio,
            }


response_cache = ResponseCache()
