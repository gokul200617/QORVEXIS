"""Infrastructure analytics service — utilization analysis, cost heuristics, recommendations.

All functions are stateless and pure.
No side effects, no threading, no imports from orchestration/lifecycle/reliability layers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.telemetry.normalizers.schema import TelemetrySnapshot

logger = logging.getLogger("qorvexis.infra_analytics")

# ---------------------------------------------------------------------------
# Heuristic constants
# ---------------------------------------------------------------------------
_HOURS_PER_MONTH = 730.0
_GPU_HOURLY_RATE_USD = 0.44          # heuristic: mid-tier GPU instance
_INFERENCE_COST_PER_REQUEST_USD = 0.0003  # fallback estimate if no cost data


# ---------------------------------------------------------------------------
# Utilization Analysis
# ---------------------------------------------------------------------------

def analyze_utilization(snapshot: TelemetrySnapshot) -> dict:
    """Classify CPU, RAM, disk and GPU into pressure tiers."""

    def _cpu_pressure(v: float | None) -> str:
        if v is None:
            return "unknown"
        if v < 50:
            return "low"
        if v < 85:
            return "medium"
        return "high"

    def _memory_pressure(v: float | None) -> str:
        if v is None:
            return "unknown"
        if v < 60:
            return "low"
        if v < 90:
            return "medium"
        return "high"

    def _disk_pressure(v: float | None) -> str:
        if v is None:
            return "unknown"
        if v < 70:
            return "low"
        if v < 90:
            return "medium"
        return "high"

    def _gpu_pressure(available: bool, v: float | None) -> str:
        if not available:
            return "unavailable"
        if v is None:
            return "unknown"
        if v < 10:
            return "idle"
        if v < 70:
            return "normal"
        return "high"

    return {
        "cpu_pressure": _cpu_pressure(snapshot.cpu_percent),
        "memory_pressure": _memory_pressure(snapshot.memory_percent),
        "disk_pressure": _disk_pressure(snapshot.disk_percent),
        "gpu_pressure": _gpu_pressure(snapshot.gpu_available, snapshot.gpu_percent),
    }


# ---------------------------------------------------------------------------
# Heuristic Cost Estimation
# ---------------------------------------------------------------------------

def compute_heuristic_cost_estimate(
    cost_summary: dict,
    dedup_summary: dict,
    cache_summary: dict,
) -> dict:
    """Extrapolate session cost data into monthly heuristic estimates.

    All values are heuristic approximations — not real billing data.
    """
    total_cost = cost_summary.get("total_estimated_cost", 0.0)
    total_requests = cost_summary.get("total_requests", 0)
    avg_cost = cost_summary.get("average_cost_per_request", 0.0) or _INFERENCE_COST_PER_REQUEST_USD

    # Extrapolate to monthly (rough: assume current session = 1 day of activity)
    heuristic_monthly_cost = round(total_cost * 30, 4)

    # Cache savings: every cache hit saved one inference call
    cache_hits = cache_summary.get("hits", 0)
    estimated_cache_savings = round(cache_hits * avg_cost, 6)

    # Dedup savings: every deduplicated request saved one inference call
    dedup_count = dedup_summary.get("duplicates_detected", 0)
    estimated_dedup_savings = round(dedup_count * avg_cost, 6)

    return {
        "heuristic_monthly_cost_estimate_usd": heuristic_monthly_cost,
        "estimated_cache_savings_usd": estimated_cache_savings,
        "estimated_dedup_savings_usd": estimated_dedup_savings,
        "total_estimated_session_cost_usd": round(total_cost, 6),
        "label": "heuristic — not real billing data",
    }


# ---------------------------------------------------------------------------
# Recommendation Engine — 7 deterministic rules
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_rec(
    rule_id: str,
    severity: str,
    title: str,
    detail: str,
    waste_usd: float = 0.0,
    savings_usd: float = 0.0,
    context: dict | None = None,
) -> dict:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "title": title,
        "detail": detail,
        "estimated_monthly_waste_usd": round(waste_usd, 2),
        "estimated_savings_usd": round(savings_usd, 2),
        "context": context or {},
        "generated_at": _utc_now_iso(),
    }


def generate_recommendations(
    snapshot: TelemetrySnapshot,
    utilization: dict,
    queue_snap: dict,
    provider_scores: dict,
    cache_snap: dict,
    dedup_snap: dict,
    settings=None,
) -> list[dict]:
    """Generate deterministic, rule-based infrastructure optimization recommendations.

    Driven by the latest telemetry snapshot and operational metrics.
    Returns a list of recommendation dicts — empty list if no rules fire.
    """
    if settings is None:
        from app.settings import settings as _settings
        settings = _settings

    recommendations: list[dict] = []
    now_iso = _utc_now_iso()

    # ── Rule 1: GPU idle waste ─────────────────────────────────────────────
    if snapshot.gpu_available and snapshot.gpu_percent is not None:
        threshold = settings.telemetry_gpu_idle_threshold
        if snapshot.gpu_percent < threshold:
            # Heuristic: idle GPU wastes full hourly rate
            idle_fraction = 1.0 - (snapshot.gpu_percent / 100.0)
            monthly_waste = round(_GPU_HOURLY_RATE_USD * _HOURS_PER_MONTH * idle_fraction, 2)
            recommendations.append(_make_rec(
                rule_id="gpu_idle",
                severity="warning",
                title="Underutilized GPU detected",
                detail=(
                    f"GPU utilization is {snapshot.gpu_percent:.1f}% — below the "
                    f"{threshold:.0f}% idle threshold. "
                    f"Estimated monthly waste from idle GPU compute: "
                    f"${monthly_waste:,.2f}."
                ),
                waste_usd=monthly_waste,
                savings_usd=monthly_waste,
                context={"gpu_percent": snapshot.gpu_percent, "threshold": threshold},
            ))

    # ── Rule 2: CPU high utilization ──────────────────────────────────────
    if snapshot.cpu_percent is not None:
        threshold = settings.telemetry_cpu_high_threshold
        if snapshot.cpu_percent > threshold:
            recommendations.append(_make_rec(
                rule_id="cpu_high",
                severity="critical",
                title="High CPU utilization",
                detail=(
                    f"CPU utilization is {snapshot.cpu_percent:.1f}% — above {threshold:.0f}% "
                    f"threshold. Inference latency degradation and request timeouts are likely. "
                    f"Review concurrent request limits or scale compute."
                ),
                waste_usd=0.0,
                savings_usd=0.0,
                context={"cpu_percent": snapshot.cpu_percent, "threshold": threshold},
            ))

    # ── Rule 3: Memory pressure ────────────────────────────────────────────
    if snapshot.memory_percent is not None:
        threshold = settings.telemetry_ram_high_threshold
        if snapshot.memory_percent > threshold:
            recommendations.append(_make_rec(
                rule_id="memory_pressure",
                severity="critical",
                title="High memory pressure",
                detail=(
                    f"RAM utilization is {snapshot.memory_percent:.1f}% — above {threshold:.0f}% "
                    f"threshold. OOM risk is elevated. Inference failures may occur. "
                    f"Reduce queue depth or increase available memory."
                ),
                waste_usd=0.0,
                savings_usd=0.0,
                context={"memory_percent": snapshot.memory_percent, "threshold": threshold},
            ))

    # ── Rule 4: Cache efficiency low ──────────────────────────────────────
    hit_ratio: float | None = None
    hits = cache_snap.get("hits", 0)
    misses = cache_snap.get("misses", 0)
    total_cache = hits + misses
    if total_cache > 0:
        hit_ratio = round((hits / total_cache) * 100, 2)

    if hit_ratio is not None:
        threshold = settings.telemetry_cache_low_threshold
        if hit_ratio < threshold:
            avg_cost = 0.0003  # fallback heuristic
            # Savings if cache ratio reached 50%
            potential_hit_increase = max(0, int(total_cache * 0.50) - hits)
            estimated_savings = round(potential_hit_increase * avg_cost * 30, 2)
            recommendations.append(_make_rec(
                rule_id="cache_efficiency_low",
                severity="warning",
                title="Low cache hit ratio",
                detail=(
                    f"Cache hit ratio is {hit_ratio:.1f}% — below {threshold:.0f}% threshold. "
                    f"Improving to 50% would reduce inference calls by ~"
                    f"{round((50 - hit_ratio), 1)}%. "
                    f"Estimated monthly savings: ${estimated_savings:,.2f}."
                ),
                waste_usd=round(potential_hit_increase * avg_cost * 30, 2),
                savings_usd=estimated_savings,
                context={"cache_hit_ratio": hit_ratio, "threshold": threshold, "hits": hits, "misses": misses},
            ))

    # ── Rule 5: High deduplication volume ─────────────────────────────────
    dedup_count = dedup_snap.get("duplicates_detected", 0)
    total_requests_dedup = dedup_snap.get("total_requests", 0)
    if total_requests_dedup > 0:
        dedup_rate = round((dedup_count / total_requests_dedup) * 100, 2)
        if dedup_rate > 20.0:
            avg_cost_saved = round(dedup_count * 0.0003 * 30, 2)
            recommendations.append(_make_rec(
                rule_id="dedup_volume_high",
                severity="info",
                title="High duplicate request volume",
                detail=(
                    f"Deduplication rate is {dedup_rate:.1f}% — {dedup_count} duplicate "
                    f"requests have been collapsed. The dedup layer is actively saving compute. "
                    f"Estimated monthly savings from deduplication: ${avg_cost_saved:,.2f}."
                ),
                waste_usd=0.0,
                savings_usd=avg_cost_saved,
                context={"dedup_rate": dedup_rate, "dedup_count": dedup_count},
            ))

    # ── Rule 6: Provider concentration ────────────────────────────────────
    providers = provider_scores.get("providers", [])
    if providers:
        total_reqs = sum(p.get("request_count", 0) for p in providers)
        if total_reqs > 0:
            for p in providers:
                p_count = p.get("request_count", 0)
                p_load = round((p_count / total_reqs) * 100, 2)
                if p_load > 85.0:
                    recommendations.append(_make_rec(
                        rule_id="provider_concentration",
                        severity="warning",
                        title=f"Provider load concentrated on {p['provider']}",
                        detail=(
                            f"{p['provider']} is handling {p_load:.1f}% of all requests. "
                            f"High concentration increases failover exposure. If {p['provider']} "
                            f"becomes unavailable, all traffic is at risk. "
                            f"Ensure the alternate provider is configured and healthy."
                        ),
                        waste_usd=0.0,
                        savings_usd=0.0,
                        context={"provider": p["provider"], "load_percent": p_load, "threshold": 85.0},
                    ))
                    break  # Only flag the highest-concentration provider

    # ── Rule 7: Queue pressure ────────────────────────────────────────────
    queue_depth = queue_snap.get("queue_depth", 0)
    queue_max = getattr(settings, "queue_max_depth", 2500)
    pressure_threshold = settings.telemetry_queue_pressure_threshold
    if queue_max > 0:
        queue_fill = queue_depth / queue_max
        if queue_fill > pressure_threshold:
            recommendations.append(_make_rec(
                rule_id="queue_pressure",
                severity="warning",
                title="High queue pressure",
                detail=(
                    f"Queue depth is {queue_depth} / {queue_max} "
                    f"({queue_fill * 100:.1f}% full) — above {pressure_threshold * 100:.0f}% "
                    f"threshold. Throughput ceiling is approaching. "
                    f"New requests may be delayed or rejected."
                ),
                waste_usd=0.0,
                savings_usd=0.0,
                context={"queue_depth": queue_depth, "queue_max": queue_max, "fill_percent": round(queue_fill * 100, 1)},
            ))

    logger.debug("infra_analytics.recommendations_generated count=%d", len(recommendations))
    return recommendations


# ---------------------------------------------------------------------------
# Idle Resource Detection
# ---------------------------------------------------------------------------

def detect_idle_resources(snapshot: TelemetrySnapshot, utilization: dict) -> dict:
    """Identify resources that are running below productive utilization."""
    idle = []

    if utilization.get("gpu_pressure") == "idle":
        idle.append({
            "resource": "gpu",
            "current_utilization_percent": snapshot.gpu_percent,
            "threshold_percent": 10.0,
        })

    if utilization.get("cpu_pressure") == "low" and snapshot.cpu_percent is not None and snapshot.cpu_percent < 10:
        idle.append({
            "resource": "cpu",
            "current_utilization_percent": snapshot.cpu_percent,
            "threshold_percent": 10.0,
        })

    return {
        "idle_resources": idle,
        "idle_count": len(idle),
    }
