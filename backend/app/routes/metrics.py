from fastapi import APIRouter, Depends
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
    get_orchestration_health,
    get_overview_metrics,
    get_provider_metrics,
    get_provider_scores,
    get_queue_metrics,
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
    return get_cost_metrics()


@router.get("/failover")
def metrics_failover() -> dict:
    return get_failover_metrics()


@router.get("/dedup")
def metrics_dedup() -> dict:
    return get_dedup_metrics()

