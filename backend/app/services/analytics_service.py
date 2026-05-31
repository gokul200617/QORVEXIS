from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.request_log import RequestLog
from app.orchestration.capacity import provider_capacity
from app.orchestration.queue_manager import queue_manager


def _percentage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def get_overview_metrics(db: Session, org_id: str | None = None) -> dict:
    q_base = db.query(RequestLog.id)
    if org_id:
        q_base = q_base.filter(RequestLog.organization_id == org_id)
        
    total_requests = q_base.count()
    failed_requests = q_base.filter(RequestLog.request_status != "success").count()
    successful_requests = total_requests - failed_requests
    
    q_lat = db.query(func.avg(RequestLog.latency_ms)).filter(RequestLog.request_status == "success")
    if org_id:
        q_lat = q_lat.filter(RequestLog.organization_id == org_id)
    average_latency = q_lat.scalar()
    
    fallback_count = q_base.filter(RequestLog.fallback_used.is_(True)).count()

    return {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "success_rate": _percentage(successful_requests, total_requests),
        "average_latency_ms": round(float(average_latency or 0), 2),
        "fallback_count": fallback_count,
        "fallback_rate": _percentage(fallback_count, total_requests),
    }


def get_provider_metrics(db: Session, org_id: str | None = None) -> dict:
    q_rows = db.query(
        RequestLog.provider_used,
        func.count(RequestLog.id).label("total_requests"),
        func.avg(RequestLog.latency_ms).label("average_latency_ms"),
        func.max(RequestLog.created_at).label("last_success_at"),
    ).filter(RequestLog.provider_used.isnot(None)).filter(RequestLog.request_status == "success")
    if org_id:
        q_rows = q_rows.filter(RequestLog.organization_id == org_id)
    rows = q_rows.group_by(RequestLog.provider_used).all()

    q_fail = db.query(
        RequestLog.original_provider,
        func.count(RequestLog.id).label("failure_count"),
    ).filter(RequestLog.request_status != "success").filter(RequestLog.original_provider.isnot(None))
    if org_id:
        q_fail = q_fail.filter(RequestLog.organization_id == org_id)
    failure_rows = q_fail.group_by(RequestLog.original_provider).all()
    
    failures_by_provider = {provider: count for provider, count in failure_rows if provider}
    
    q_fall = db.query(
        RequestLog.original_provider,
        func.count(RequestLog.id).label("fallback_failure_count"),
    ).filter(RequestLog.request_status == "success").filter(RequestLog.fallback_used.is_(True)).filter(RequestLog.original_provider.isnot(None))
    if org_id:
        q_fall = q_fall.filter(RequestLog.organization_id == org_id)
    fallback_rows = q_fall.group_by(RequestLog.original_provider).all()
    
    for provider, count in fallback_rows:
        if provider:
            failures_by_provider[provider] = failures_by_provider.get(provider, 0) + count

    providers = []
    for provider, total_requests, average_latency_ms, last_success_at in rows:
        failure_count = failures_by_provider.get(provider, 0)
        attempts = total_requests + failure_count
        providers.append(
            {
                "provider": provider,
                "total_requests": total_requests,
                "failure_count": failure_count,
                "success_rate": _percentage(total_requests, attempts),
                "average_latency_ms": round(float(average_latency_ms or 0), 2),
                "last_success_at": last_success_at.isoformat() if last_success_at else None,
            }
        )

    from app.services.historical_metrics import historical_metrics
    for provider in providers:
        historical_metrics.record(
            "provider_latency",
            {
                "provider": provider["provider"],
                "average_latency_ms": provider["average_latency_ms"],
                "success_rate": provider["success_rate"],
                "failure_count": provider["failure_count"],
            },
        )
    return {"providers": providers}


def get_latency_metrics(db: Session, org_id: str | None = None) -> dict:
    q_overall = db.query(func.avg(RequestLog.latency_ms)).filter(RequestLog.request_status == "success")
    if org_id:
        q_overall = q_overall.filter(RequestLog.organization_id == org_id)
    overall_average = q_overall.scalar()
    
    q_rows = db.query(
        RequestLog.provider_used,
        func.avg(RequestLog.latency_ms).label("average_latency_ms"),
        func.min(RequestLog.latency_ms).label("min_latency_ms"),
        func.max(RequestLog.latency_ms).label("max_latency_ms"),
    ).filter(RequestLog.provider_used.isnot(None)).filter(RequestLog.request_status == "success")
    if org_id:
        q_rows = q_rows.filter(RequestLog.organization_id == org_id)
    rows = q_rows.group_by(RequestLog.provider_used).all()

    return {
        "average_latency_ms": round(float(overall_average or 0), 2),
        "by_provider": [
            {
                "provider": provider,
                "average_latency_ms": round(float(average_latency_ms or 0), 2),
                "min_latency_ms": min_latency_ms or 0,
                "max_latency_ms": max_latency_ms or 0,
            }
            for provider, average_latency_ms, min_latency_ms, max_latency_ms in rows
        ],
    }


def get_category_metrics(db: Session, org_id: str | None = None) -> dict:
    q_total = db.query(func.count(RequestLog.id))
    if org_id:
        q_total = q_total.filter(RequestLog.organization_id == org_id)
    total_requests = q_total.scalar() or 0
    
    q_rows = db.query(
        RequestLog.request_category,
        func.count(RequestLog.id).label("total_requests"),
        func.sum(case((RequestLog.request_status == "success", 1), else_=0)).label("successful_requests"),
    )
    if org_id:
        q_rows = q_rows.filter(RequestLog.organization_id == org_id)
    rows = q_rows.group_by(RequestLog.request_category).all()

    return {
        "categories": [
            {
                "category": category or "unclassified",
                "total_requests": total,
                "successful_requests": successful or 0,
                "percentage": _percentage(total, total_requests),
            }
            for category, total, successful in rows
        ]
    }


def get_queue_metrics() -> dict:
    snapshot = queue_manager.snapshot()
    from app.services.historical_metrics import historical_metrics
    historical_metrics.record(
        "queue_depth",
        {
            "queue_depth": snapshot["queue_depth"],
            "active_executions": snapshot["active_executions"],
            "queue_anomalies": snapshot.get("queue_anomalies", 0),
        },
    )
    return snapshot


def get_capacity_metrics() -> dict:
    return provider_capacity.snapshot()


def get_throughput_metrics(db: Session, org_id: str | None = None) -> dict:
    one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    
    q_base = db.query(func.count(RequestLog.id))
    if org_id:
        q_base = q_base.filter(RequestLog.organization_id == org_id)
        
    recent_count = q_base.filter(RequestLog.created_at >= one_minute_ago).scalar() or 0
    completed_count = q_base.filter(RequestLog.lifecycle_state == "completed").scalar() or 0
    cancelled_count = q_base.filter(RequestLog.lifecycle_state == "cancelled").scalar() or 0
    
    q_avg_qw = db.query(func.avg(RequestLog.queue_wait_ms))
    q_avg_ex = db.query(func.avg(RequestLog.execution_duration_ms))
    if org_id:
        q_avg_qw = q_avg_qw.filter(RequestLog.organization_id == org_id)
        q_avg_ex = q_avg_ex.filter(RequestLog.organization_id == org_id)
    avg_queue_wait = q_avg_qw.scalar()
    avg_execution = q_avg_ex.scalar()

    q_prov = db.query(
        RequestLog.provider_used,
        func.count(RequestLog.id).label("completed"),
    ).filter(RequestLog.lifecycle_state == "completed").filter(RequestLog.provider_used.isnot(None))
    if org_id:
        q_prov = q_prov.filter(RequestLog.organization_id == org_id)
    provider_rows = q_prov.group_by(RequestLog.provider_used).all()

    return {
        "requests_per_minute": recent_count,
        "average_queue_wait_ms": round(float(avg_queue_wait or 0), 2),
        "average_execution_duration_ms": round(float(avg_execution or 0), 2),
        "request_completion_count": completed_count,
        "request_cancellation_count": cancelled_count,
        "provider_throughput": [
            {"provider": provider, "completed_requests": completed}
            for provider, completed in provider_rows
        ],
    }


def get_lifecycle_metrics(db: Session, org_id: str | None = None) -> dict:
    q_state = db.query(RequestLog.lifecycle_state, func.count(RequestLog.id))
    q_pri = db.query(RequestLog.request_priority, func.count(RequestLog.id))
    if org_id:
        q_state = q_state.filter(RequestLog.organization_id == org_id)
        q_pri = q_pri.filter(RequestLog.organization_id == org_id)
        
    rows = q_state.group_by(RequestLog.lifecycle_state).all()
    priority_rows = q_pri.group_by(RequestLog.request_priority).all()
    
    return {
        "states": [{"state": state or "unknown", "count": count} for state, count in rows],
        "priorities": [{"priority": priority or "unknown", "count": count} for priority, count in priority_rows],
    }


# ---------------------------------------------------------------------------
# Phase 5 — Operational intelligence metrics
# ---------------------------------------------------------------------------

def get_cache_metrics() -> dict:
    from app.services.response_cache import response_cache
    return response_cache.snapshot()

def get_provider_scores() -> dict:
    from app.services.provider_scorer import provider_scorer
    return provider_scorer.get_all_scores()

def get_orchestration_health() -> dict:
    from app.services.ops_scorer import compute_orchestration_health
    from app.services.historical_metrics import historical_metrics

    health = compute_orchestration_health()
    historical_metrics.record("orchestration_health", health)
    return health

def get_cost_metrics() -> dict:
    from app.services.cost_tracker import cost_tracker
    return cost_tracker.get_cost_summary()

def get_failover_metrics() -> dict:
    from app.services.failover_manager import failover_manager
    return failover_manager.snapshot()

def get_dedup_metrics() -> dict:
    from app.services.dedup_tracker import dedup_tracker
    return dedup_tracker.snapshot()

def get_reliability_metrics(db: Session, org_id: str | None = None) -> dict:
    from app.observability.diagnostics import detect_stale_requests
    from app.reliability.integrity import integrity_registry
    from app.reliability.reconciliation import reconciliation_registry
    from app.reliability.recovery import recovery_registry
    from app.services.historical_metrics import historical_metrics
    from app.services.session_service import get_session_memory_metrics

    overview = get_overview_metrics(db, org_id=org_id)
    return {
        "orchestration_health": get_orchestration_health(),
        "integrity": integrity_registry.snapshot(),
        "recovery": recovery_registry.snapshot(),
        "reconciliation": reconciliation_registry.snapshot(),
        "queue": get_queue_metrics(),
        "stale_requests": detect_stale_requests(db), # Needs org_id? Usually global diag
        "session_memory": get_session_memory_metrics(db, org_id=org_id),
        "success_rate": overview["success_rate"],
        "failure_rate": round(100 - overview["success_rate"], 2),
        "history": historical_metrics.snapshot(),
    }

def get_lifecycle_integrity_metrics(db: Session, org_id: str | None = None) -> dict:
    from app.observability.diagnostics import get_lifecycle_transition_view
    from app.reliability.integrity import integrity_registry

    return {
        **get_lifecycle_metrics(db, org_id=org_id),
        **get_lifecycle_transition_view(db),
        "integrity": integrity_registry.snapshot(),
    }

def get_recovery_metrics(db: Session) -> dict:
    from app.observability.diagnostics import detect_stale_requests
    from app.reliability.recovery import recovery_registry
    from app.reliability.reconciliation import reconciliation_registry

    return {
        "status": "healthy",
        **recovery_registry.snapshot(),
        "reconciliation": reconciliation_registry.snapshot(),
        "stale_requests": detect_stale_requests(db),
        "queue": queue_manager.diagnostics(db),
    }

def get_diagnostics_metrics(db: Session) -> dict:
    from app.observability.diagnostics import get_diagnostics
    return get_diagnostics(db)
