"""Adaptive failover manager — provider health monitoring with cooldown logic."""

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from time import monotonic

from app.settings import settings

logger = logging.getLogger("qorvexis.failover")

_FAILURE_WINDOW_SECONDS = 300  # 5-minute rolling window
_FAILURE_RATE_THRESHOLD = 0.50
_CONSECUTIVE_FAILURE_THRESHOLD = 3


@dataclass
class _ProviderHealth:
    events: deque = field(default_factory=lambda: deque())  # (timestamp, success: bool)
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    total_cooldowns: int = 0


class FailoverManager:
    """Provider health-aware failover with cooldown logic.

    Monitors per-provider failure windows (rolling 5-minute window).
    Triggers cooldown when failure rate exceeds 50% OR 3+ consecutive failures.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: dict[str, _ProviderHealth] = {}

    def _ensure_provider(self, provider: str) -> _ProviderHealth:
        if provider not in self._providers:
            self._providers[provider] = _ProviderHealth()
        return self._providers[provider]

    def _prune_window(self, health: _ProviderHealth) -> None:
        cutoff = monotonic() - _FAILURE_WINDOW_SECONDS
        while health.events and health.events[0][0] < cutoff:
            health.events.popleft()

    def _check_cooldown_trigger(self, provider: str, health: _ProviderHealth) -> None:
        self._prune_window(health)
        if not health.events:
            return

        failure_count = sum(1 for _ts, success in health.events if not success)
        failure_rate = failure_count / len(health.events)

        should_cooldown = (
            failure_rate >= _FAILURE_RATE_THRESHOLD
            or health.consecutive_failures >= _CONSECUTIVE_FAILURE_THRESHOLD
        )

        if should_cooldown and not self.is_cooled_down_unsafe(health):
            health.cooldown_until = monotonic() + settings.provider_cooldown_seconds
            health.total_cooldowns += 1
            logger.warning(
                "failover.cooldown_activated provider=%s failure_rate=%.2f consecutive=%s duration=%ss",
                provider,
                failure_rate,
                health.consecutive_failures,
                settings.provider_cooldown_seconds,
            )

    @staticmethod
    def is_cooled_down_unsafe(health: _ProviderHealth) -> bool:
        return monotonic() < health.cooldown_until

    def record_success(self, provider: str) -> None:
        with self._lock:
            health = self._ensure_provider(provider)
            health.events.append((monotonic(), True))
            health.consecutive_failures = 0
        logger.info("failover.record_success provider=%s", provider)

    def record_failure(self, provider: str) -> None:
        with self._lock:
            health = self._ensure_provider(provider)
            health.events.append((monotonic(), False))
            health.consecutive_failures += 1
            self._check_cooldown_trigger(provider, health)
        logger.info(
            "failover.record_failure provider=%s consecutive=%s",
            provider,
            health.consecutive_failures,
        )

    def is_cooled_down(self, provider: str) -> bool:
        with self._lock:
            health = self._providers.get(provider)
            if health is None:
                return False
            return self.is_cooled_down_unsafe(health)

    def get_best_provider(self, preferred: str, fallback: str) -> str:
        with self._lock:
            pref_health = self._providers.get(preferred)
            fall_health = self._providers.get(fallback)

            pref_cooled = pref_health and self.is_cooled_down_unsafe(pref_health)
            fall_cooled = fall_health and self.is_cooled_down_unsafe(fall_health)

            if pref_cooled and not fall_cooled:
                logger.info(
                    "failover.provider_swap preferred=%s fallback=%s reason=cooldown",
                    preferred,
                    fallback,
                )
                return fallback
            return preferred

    def snapshot(self) -> dict:
        with self._lock:
            providers = []
            for provider, health in self._providers.items():
                self._prune_window(health)
                total_events = len(health.events)
                failure_count = sum(1 for _ts, success in health.events if not success)
                failure_rate = (failure_count / total_events * 100) if total_events else 0
                is_cooled = self.is_cooled_down_unsafe(health)
                remaining = max(0, round(health.cooldown_until - monotonic(), 1)) if is_cooled else 0

                providers.append(
                    {
                        "provider": provider,
                        "is_cooled_down": is_cooled,
                        "cooldown_remaining_seconds": remaining,
                        "total_cooldowns": health.total_cooldowns,
                        "consecutive_failures": health.consecutive_failures,
                        "window_events": total_events,
                        "window_failure_rate": round(failure_rate, 2),
                    }
                )
            return {"providers": providers}


failover_manager = FailoverManager()
