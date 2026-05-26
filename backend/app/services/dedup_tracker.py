"""Request deduplication tracker — detects identical prompts within a sliding window."""

import hashlib
import logging
import threading
from time import monotonic

from app.settings import settings

logger = logging.getLogger("qorvexis.dedup")


class DedupTracker:
    """Lightweight duplicate request detector.

    Maintains a sliding window of recent prompt hashes. If an identical
    (whitespace/case-normalized) prompt is seen within
    ``settings.dedup_window_seconds``, it is flagged as a duplicate.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recent: dict[str, float] = {}  # hash -> timestamp
        self._duplicates_detected = 0
        self._total_checked = 0

    @staticmethod
    def _normalize_and_hash(prompt: str) -> str:
        normalized = " ".join(prompt.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _prune_expired(self) -> None:
        now = monotonic()
        window = settings.dedup_window_seconds
        expired_keys = [
            key for key, timestamp in self._recent.items() if (now - timestamp) > window
        ]
        for key in expired_keys:
            del self._recent[key]

    def is_duplicate(self, prompt: str) -> bool:
        key = self._normalize_and_hash(prompt)
        with self._lock:
            self._prune_expired()
            self._total_checked += 1
            if key in self._recent:
                self._duplicates_detected += 1
                logger.info("dedup.duplicate_detected key=%s", key[:12])
                return True
            return False

    def record(self, prompt: str) -> None:
        key = self._normalize_and_hash(prompt)
        with self._lock:
            self._recent[key] = monotonic()
        logger.info("dedup.record key=%s", key[:12])

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active_entries": len(self._recent),
                "window_seconds": settings.dedup_window_seconds,
                "duplicates_detected": self._duplicates_detected,
                "total_checked": self._total_checked,
                "dedup_rate": round(
                    (self._duplicates_detected / self._total_checked) * 100, 2
                )
                if self._total_checked
                else 0,
            }


dedup_tracker = DedupTracker()
