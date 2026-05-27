"""Phase 7 — Telemetry API routes.

New endpoints:
  GET /metrics/infrastructure  — full system snapshot + utilization analysis
  GET /metrics/gpu             — GPU-specific metrics
  GET /metrics/recommendations — deterministic optimization recommendations

All routes:
  - Return {"status": "telemetry_unavailable"} on any unhandled failure
  - Never affect orchestration or queue state
  - Include last_updated_at in every response
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.settings import settings

logger = logging.getLogger("qorvexis.routes.telemetry")

router = APIRouter(prefix="/metrics", tags=["telemetry"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unavailable(reason: str = "collector_error") -> dict:
    return {
        "status": "telemetry_unavailable",
        "reason": reason,
        "last_updated_at": None,
    }


@router.get("/infrastructure")
def metrics_infrastructure(db: Session = Depends(get_db)) -> dict:
    """Full local infrastructure telemetry snapshot with utilization analysis."""
    if not settings.telemetry_enabled:
        return _unavailable("telemetry_disabled")

    try:
        from app.services.infrastructure_analytics_service import (
            analyze_utilization,
            detect_idle_resources,
        )
        from app.telemetry.providers.telemetry_provider import telemetry_provider

        snapshot = telemetry_provider.get_snapshot(db=db)
        utilization = analyze_utilization(snapshot)
        idle = detect_idle_resources(snapshot, utilization)

        result = snapshot.to_dict()
        result["utilization_analysis"] = utilization
        result["idle_resources"] = idle
        return result

    except Exception as exc:
        logger.warning("routes.infrastructure_metrics_failed error=%s", exc)
        return _unavailable(str(exc)[:128])


@router.get("/gpu")
def metrics_gpu() -> dict:
    """GPU-specific telemetry metrics."""
    if not settings.telemetry_enabled:
        return {**_unavailable("telemetry_disabled"), "available": False}

    try:
        from app.telemetry.collectors.gpu_collector import collect_gpu_metrics

        gpu_data = collect_gpu_metrics()
        gpu_data["last_updated_at"] = _utc_now_iso()
        return gpu_data

    except Exception as exc:
        logger.warning("routes.gpu_metrics_failed error=%s", exc)
        return {"available": False, "reason": str(exc)[:128], "last_updated_at": _utc_now_iso()}


@router.get("/recommendations")
def metrics_recommendations() -> dict:
    """Deterministic infrastructure optimization recommendations."""
    if not settings.telemetry_enabled:
        return {
            "count": 0,
            "recommendations": [],
            "last_updated_at": _utc_now_iso(),
            "generated_at": _utc_now_iso(),
            "status": "telemetry_disabled",
        }

    try:
        from app.orchestration.queue_manager import queue_manager
        from app.services.dedup_tracker import dedup_tracker
        from app.services.infrastructure_analytics_service import (
            analyze_utilization,
            generate_recommendations,
        )
        from app.services.provider_scorer import provider_scorer
        from app.services.response_cache import response_cache
        from app.telemetry.providers.telemetry_provider import telemetry_provider

        # Use cached snapshot if available to avoid double-collect
        snapshot = telemetry_provider.get_latest()
        if snapshot is None:
            snapshot = telemetry_provider.get_snapshot()

        utilization = analyze_utilization(snapshot)
        queue_snap = queue_manager.snapshot()
        provider_scores = provider_scorer.get_all_scores()
        cache_snap = response_cache.snapshot()
        dedup_snap = dedup_tracker.snapshot()

        recs = generate_recommendations(
            snapshot=snapshot,
            utilization=utilization,
            queue_snap=queue_snap,
            provider_scores=provider_scores,
            cache_snap=cache_snap,
            dedup_snap=dedup_snap,
        )

        now = _utc_now_iso()
        return {
            "count": len(recs),
            "last_updated_at": now,
            "generated_at": now,
            "recommendations": recs,
        }

    except Exception as exc:
        logger.warning("routes.recommendations_failed error=%s", exc)
        return {
            "count": 0,
            "recommendations": [],
            "last_updated_at": _utc_now_iso(),
            "generated_at": _utc_now_iso(),
            "status": "error",
            "reason": str(exc)[:128],
        }
