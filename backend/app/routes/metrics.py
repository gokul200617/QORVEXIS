from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.analytics_service import (
    get_cache_metrics,
    get_category_metrics,
    get_capacity_metrics,
    get_cost_metrics,
    get_dedup_metrics,
    get_failover_metrics,
    get_latency_metrics,
    get_lifecycle_metrics,
    get_lifecycle_integrity_metrics,
    get_orchestration_health,
    get_overview_metrics,
    get_provider_metrics,
    get_provider_scores,
    get_queue_metrics,
    get_recovery_metrics,
    get_reliability_metrics,
    get_diagnostics_metrics,
    get_throughput_metrics,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/overview")
def metrics_overview(db: Session = Depends(get_db)) -> dict:
    return get_overview_metrics(db)


@router.get("/providers")
def metrics_providers(db: Session = Depends(get_db)) -> dict:
    return get_provider_metrics(db)


@router.get("/latency")
def metrics_latency(db: Session = Depends(get_db)) -> dict:
    return get_latency_metrics(db)


@router.get("/categories")
def metrics_categories(db: Session = Depends(get_db)) -> dict:
    return get_category_metrics(db)


@router.get("/queue")
def metrics_queue() -> dict:
    return get_queue_metrics()


@router.get("/capacity")
def metrics_capacity() -> dict:
    return get_capacity_metrics()


@router.get("/throughput")
def metrics_throughput(db: Session = Depends(get_db)) -> dict:
    return get_throughput_metrics(db)


@router.get("/lifecycle")
def metrics_lifecycle(db: Session = Depends(get_db)) -> dict:
    return get_lifecycle_metrics(db)


# Phase 5 — Operational intelligence endpoints

@router.get("/cache")
def metrics_cache() -> dict:
    return get_cache_metrics()


@router.get("/providers/score")
def metrics_provider_scores() -> dict:
    return get_provider_scores()


@router.get("/orchestration/health")
def metrics_orchestration_health() -> dict:
    return get_orchestration_health()


@router.get("/costs")
def metrics_costs() -> dict:
    base = get_cost_metrics()
    try:
        from app.services.dedup_tracker import dedup_tracker
        from app.services.infrastructure_analytics_service import compute_heuristic_cost_estimate
        from app.services.response_cache import response_cache

        base["infrastructure_cost_heuristics"] = compute_heuristic_cost_estimate(
            cost_summary=base,
            dedup_summary=dedup_tracker.snapshot(),
            cache_summary=response_cache.snapshot(),
        )
    except Exception as exc:
        import logging
        logging.getLogger("qorvexis.routes.metrics").warning(
            "metrics_costs.heuristics_failed error=%s", exc
        )
        base["infrastructure_cost_heuristics"] = {"label": "heuristic unavailable"}
    return base


@router.get("/failover")
def metrics_failover() -> dict:
    return get_failover_metrics()


@router.get("/dedup")
def metrics_dedup() -> dict:
    return get_dedup_metrics()


# Phase 6 - Reliability hardening endpoints

@router.get("/reliability")
def metrics_reliability(db: Session = Depends(get_db)) -> dict:
    try:
        return get_reliability_metrics(db)
    except SQLAlchemyError as exc:
        from app.orchestration.queue_manager import queue_manager
        from app.reliability.integrity import integrity_registry
        from app.reliability.reconciliation import reconciliation_registry
        from app.reliability.recovery import recovery_registry
        from app.services.historical_metrics import historical_metrics

        return {
            "status": "degraded",
            "database_error": str(exc.__cause__ or exc),
            "integrity": integrity_registry.snapshot(),
            "recovery": recovery_registry.snapshot(),
            "reconciliation": reconciliation_registry.snapshot(),
            "queue": queue_manager.snapshot(),
            "history": historical_metrics.snapshot(),
        }


@router.get("/lifecycle/integrity")
def metrics_lifecycle_integrity(db: Session = Depends(get_db)) -> dict:
    try:
        return get_lifecycle_integrity_metrics(db)
    except SQLAlchemyError as exc:
        from app.reliability.integrity import integrity_registry

        return {
            "status": "degraded",
            "database_error": str(exc.__cause__ or exc),
            "states": [],
            "priorities": [],
            "transitions": [],
            "integrity": integrity_registry.snapshot(),
        }


@router.get("/recovery")
def metrics_recovery(db: Session = Depends(get_db)) -> dict:
    try:
        return get_recovery_metrics(db)
    except SQLAlchemyError as exc:
        from app.orchestration.queue_manager import queue_manager
        from app.reliability.reconciliation import reconciliation_registry
        from app.reliability.recovery import recovery_registry

        return {
            "status": "degraded",
            "database_error": str(exc.__cause__ or exc),
            **recovery_registry.snapshot(),
            "reconciliation": reconciliation_registry.snapshot(),
            "stale_requests": [],
            "queue": queue_manager.diagnostics(),
        }


@router.get("/diagnostics")
def metrics_diagnostics(db: Session = Depends(get_db)) -> dict:
    try:
        return get_diagnostics_metrics(db)
    except SQLAlchemyError as exc:
        from app.orchestration.queue_manager import queue_manager
        from app.reliability.integrity import integrity_registry
        from app.reliability.reconciliation import reconciliation_registry
        from app.services.response_cache import response_cache
        from app.services.failover_manager import failover_manager

        return {
            "status": "degraded",
            "database_error": str(exc.__cause__ or exc),
            "queue": queue_manager.diagnostics(),
            "integrity": integrity_registry.snapshot(),
            "reconciliation": reconciliation_registry.snapshot(),
            "cache": response_cache.snapshot(),
            "provider_cooldowns": failover_manager.snapshot(),
            "timelines": [],
            "transitions": [],
            "stale_requests": [],
        }
