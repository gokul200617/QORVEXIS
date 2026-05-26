"""Operational scoring engine — composite orchestration health scoring."""

import logging

from app.orchestration.capacity import provider_capacity
from app.orchestration.queue_manager import queue_manager
from app.services.cost_tracker import cost_tracker
from app.services.dedup_tracker import dedup_tracker
from app.services.failover_manager import failover_manager
from app.services.provider_scorer import provider_scorer
from app.services.response_cache import response_cache

logger = logging.getLogger("qorvexis.ops_scorer")

_WEIGHT_PROVIDER_RELIABILITY = 0.25
_WEIGHT_QUEUE_EFFICIENCY = 0.20
_WEIGHT_EXECUTION_EFFICIENCY = 0.20
_WEIGHT_CACHE_EFFICIENCY = 0.15
_WEIGHT_FAILOVER_HEALTH = 0.20

_QUEUE_DEPTH_BASELINE = 10
_LATENCY_BASELINE_MS = 5000


def _compute_provider_reliability_score() -> float:
    scores = provider_scorer.get_all_scores()
    providers = scores.get("providers", [])
    if not providers:
        return 50.0
    return sum(p["score"] for p in providers) / len(providers)


def _compute_queue_efficiency_score() -> float:
    snap = queue_manager.snapshot()
    depth = snap.get("queue_depth", 0)
    if depth == 0:
        return 100.0
    ratio = max(0.0, 1.0 - (depth / _QUEUE_DEPTH_BASELINE))
    return ratio * 100


def _compute_execution_efficiency_score() -> float:
    snap = provider_capacity.snapshot()
    providers = snap.get("providers", [])
    if not providers:
        return 50.0
    latencies = [p["average_execution_ms"] for p in providers if p["average_execution_ms"] > 0]
    if not latencies:
        return 50.0
    avg_latency = sum(latencies) / len(latencies)
    ratio = max(0.0, 1.0 - (avg_latency / _LATENCY_BASELINE_MS))
    return ratio * 100


def _compute_cache_efficiency_score() -> float:
    snap = response_cache.snapshot()
    return snap.get("hit_ratio", 0)


def _compute_failover_health_score() -> float:
    snap = failover_manager.snapshot()
    providers = snap.get("providers", [])
    if not providers:
        return 100.0
    cooled_count = sum(1 for p in providers if p["is_cooled_down"])
    if cooled_count == 0:
        return 100.0
    healthy_ratio = 1.0 - (cooled_count / len(providers))
    return healthy_ratio * 100


def compute_orchestration_health() -> dict:
    """Compute composite orchestration health score (0–100)."""
    provider_reliability = _compute_provider_reliability_score()
    queue_efficiency = _compute_queue_efficiency_score()
    execution_efficiency = _compute_execution_efficiency_score()
    cache_efficiency = _compute_cache_efficiency_score()
    failover_health = _compute_failover_health_score()

    composite = (
        provider_reliability * _WEIGHT_PROVIDER_RELIABILITY
        + queue_efficiency * _WEIGHT_QUEUE_EFFICIENCY
        + execution_efficiency * _WEIGHT_EXECUTION_EFFICIENCY
        + cache_efficiency * _WEIGHT_CACHE_EFFICIENCY
        + failover_health * _WEIGHT_FAILOVER_HEALTH
    )

    composite = max(0.0, min(100.0, composite))

    result = {
        "orchestration_health_score": round(composite, 2),
        "components": {
            "provider_reliability": round(provider_reliability, 2),
            "queue_efficiency": round(queue_efficiency, 2),
            "execution_efficiency": round(execution_efficiency, 2),
            "cache_efficiency": round(cache_efficiency, 2),
            "failover_health": round(failover_health, 2),
        },
        "dedup_stats": dedup_tracker.snapshot(),
        "cost_summary": cost_tracker.get_cost_summary(),
    }

    logger.info(
        "ops_scorer.health_computed score=%.2f",
        composite,
    )
    return result
