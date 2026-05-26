"""Provider scoring engine — heuristic composite scoring for provider selection."""

import logging
import threading
from dataclasses import dataclass, field
from time import monotonic

logger = logging.getLogger("qorvexis.scoring")

_SCORE_WEIGHT_SUCCESS_RATE = 0.40
_SCORE_WEIGHT_LATENCY = 0.30
_SCORE_WEIGHT_FAILURE_PENALTY = 0.20
_SCORE_WEIGHT_THROUGHPUT = 0.10

_LATENCY_BASELINE_MS = 5000
_THROUGHPUT_BASELINE = 100


@dataclass
class _ProviderStats:
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: int = 0
    request_count: int = 0
    last_updated: float = field(default_factory=monotonic)


class ProviderScorer:
    """Thread-safe, in-memory provider scoring engine.

    Computes a composite score (0–100) per provider based on:
    - Success rate (40%)
    - Latency score (30%)  — lower average latency = higher score
    - Failure penalty (20%) — fewer failures = higher score
    - Throughput bonus (10%) — more completed requests = higher score
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: dict[str, _ProviderStats] = {}

    def _ensure_provider(self, provider: str) -> _ProviderStats:
        if provider not in self._stats:
            self._stats[provider] = _ProviderStats()
        return self._stats[provider]

    def record_success(self, provider: str, latency_ms: int) -> None:
        with self._lock:
            stats = self._ensure_provider(provider)
            stats.success_count += 1
            stats.request_count += 1
            stats.total_latency_ms += latency_ms
            stats.last_updated = monotonic()
        logger.info(
            "scoring.record_success provider=%s latency_ms=%s",
            provider,
            latency_ms,
        )

    def record_failure(self, provider: str) -> None:
        with self._lock:
            stats = self._ensure_provider(provider)
            stats.failure_count += 1
            stats.request_count += 1
            stats.last_updated = monotonic()
        logger.info("scoring.record_failure provider=%s", provider)

    def get_score(self, provider: str) -> float:
        with self._lock:
            stats = self._stats.get(provider)
            if not stats or stats.request_count == 0:
                return 50.0  # neutral default
            return self._compute_score(stats)

    def get_all_scores(self) -> dict:
        with self._lock:
            providers = []
            for provider, stats in self._stats.items():
                score = self._compute_score(stats) if stats.request_count > 0 else 50.0
                avg_latency = (
                    stats.total_latency_ms / stats.request_count
                    if stats.request_count
                    else 0
                )
                providers.append(
                    {
                        "provider": provider,
                        "score": round(score, 2),
                        "success_count": stats.success_count,
                        "failure_count": stats.failure_count,
                        "request_count": stats.request_count,
                        "average_latency_ms": round(avg_latency, 2),
                        "success_rate": round(
                            (stats.success_count / stats.request_count) * 100, 2
                        )
                        if stats.request_count
                        else 0,
                    }
                )
            return {"providers": providers}

    def get_ranked_providers(self) -> list[str]:
        with self._lock:
            scored = []
            for provider, stats in self._stats.items():
                score = self._compute_score(stats) if stats.request_count > 0 else 50.0
                scored.append((provider, score))
            scored.sort(key=lambda item: item[1], reverse=True)
            return [provider for provider, _score in scored]

    @staticmethod
    def _compute_score(stats: _ProviderStats) -> float:
        total = stats.request_count
        if total == 0:
            return 50.0

        success_rate = stats.success_count / total
        success_component = success_rate * 100 * _SCORE_WEIGHT_SUCCESS_RATE

        avg_latency = stats.total_latency_ms / total
        latency_ratio = max(0.0, 1.0 - (avg_latency / _LATENCY_BASELINE_MS))
        latency_component = latency_ratio * 100 * _SCORE_WEIGHT_LATENCY

        failure_ratio = stats.failure_count / total
        failure_component = (1.0 - failure_ratio) * 100 * _SCORE_WEIGHT_FAILURE_PENALTY

        throughput_ratio = min(1.0, total / _THROUGHPUT_BASELINE)
        throughput_component = throughput_ratio * 100 * _SCORE_WEIGHT_THROUGHPUT

        return max(0.0, min(100.0, success_component + latency_component + failure_component + throughput_component))


provider_scorer = ProviderScorer()
