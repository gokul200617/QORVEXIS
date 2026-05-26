import threading
from collections import defaultdict
from datetime import datetime, timezone

from app.settings import settings


class ProviderCapacityTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._limits = {
            "gemini": settings.gemini_max_concurrency,
            "groq": settings.groq_max_concurrency,
        }
        self._semaphores = {
            provider: threading.Semaphore(limit)
            for provider, limit in self._limits.items()
        }
        self._active = defaultdict(int)
        self._queued = defaultdict(int)
        self._execution_totals = defaultdict(int)
        self._execution_counts = defaultdict(int)
        self._failure_counts = defaultdict(int)
        self._last_execution = {}

    def acquire(self, provider: str) -> threading.Semaphore:
        return self._semaphores.get(provider, threading.Semaphore(1))

    def mark_queued(self, provider: str) -> None:
        with self._lock:
            self._queued[provider] += 1

    def mark_dequeued(self, provider: str) -> None:
        with self._lock:
            self._queued[provider] = max(0, self._queued[provider] - 1)

    def mark_start(self, provider: str) -> None:
        with self._lock:
            self._active[provider] += 1

    def mark_complete(self, provider: str, duration_ms: int, failed: bool = False) -> None:
        with self._lock:
            self._active[provider] = max(0, self._active[provider] - 1)
            self._execution_totals[provider] += duration_ms
            self._execution_counts[provider] += 1
            self._last_execution[provider] = datetime.now(timezone.utc)
            if failed:
                self._failure_counts[provider] += 1

    def snapshot(self) -> dict:
        with self._lock:
            providers = []
            for provider, limit in self._limits.items():
                count = self._execution_counts[provider]
                failures = self._failure_counts[provider]
                avg_ms = self._execution_totals[provider] / count if count else 0
                providers.append(
                    {
                        "provider": provider,
                        "active_requests": self._active[provider],
                        "queued_requests": self._queued[provider],
                        "average_execution_ms": round(avg_ms, 2),
                        "failure_rate": round((failures / count) * 100, 2) if count else 0,
                        "concurrency_level": limit,
                        "last_execution_at": self._last_execution.get(provider).isoformat()
                        if self._last_execution.get(provider)
                        else None,
                    }
                )
            return {"providers": providers}


provider_capacity = ProviderCapacityTracker()
