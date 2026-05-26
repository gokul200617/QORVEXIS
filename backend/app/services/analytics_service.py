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


def get_overview_metrics(db: Session) -> dict:
    total_requests = db.query(func.count(RequestLog.id)).scalar() or 0
    failed_requests = (
        db.query(func.count(RequestLog.id))
        .filter(RequestLog.request_status != "success")
        .scalar()
        or 0
    )
    successful_requests = total_requests - failed_requests
    average_latency = (
        db.query(func.avg(RequestLog.latency_ms))
        .filter(RequestLog.request_status == "success")
        .scalar()
    )
    fallback_count = (
        db.query(func.count(RequestLog.id))
        .filter(RequestLog.fallback_used.is_(True))
        .scalar()
        or 0
    )

    return {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "success_rate": _percentage(successful_requests, total_requests),
        "average_latency_ms": round(float(average_latency or 0), 2),
        "fallback_count": fallback_count,
        "fallback_rate": _percentage(fallback_count, total_requests),
    }


def get_provider_metrics(db: Session) -> dict:
    rows = (
        db.query(
            RequestLog.provider_used,
            func.count(RequestLog.id).label("total_requests"),
            func.avg(RequestLog.latency_ms).label("average_latency_ms"),
            func.max(RequestLog.created_at).label("last_success_at"),
        )
        .filter(RequestLog.provider_used.isnot(None))
        .filter(RequestLog.request_status == "success")
        .group_by(RequestLog.provider_used)
        .all()
    )

    failure_rows = (
        db.query(
            RequestLog.original_provider,
            func.count(RequestLog.id).label("failure_count"),
        )
        .filter(RequestLog.request_status != "success")
        .filter(RequestLog.original_provider.isnot(None))
        .group_by(RequestLog.original_provider)
        .all()
    )
    failures_by_provider = {
        provider: count for provider, count in failure_rows if provider
    }
    fallback_rows = (
        db.query(
            RequestLog.original_provider,
            func.count(RequestLog.id).label("fallback_failure_count"),
        )
        .filter(RequestLog.request_status == "success")
        .filter(RequestLog.fallback_used.is_(True))
        .filter(RequestLog.original_provider.isnot(None))
        .group_by(RequestLog.original_provider)
        .all()
    )
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
                "last_success_at": last_success_at.isoformat()
                if last_success_at
                else None,
            }
        )

    return {"providers": providers}


def get_latency_metrics(db: Session) -> dict:
    overall_average = (
        db.query(func.avg(RequestLog.latency_ms))
        .filter(RequestLog.request_status == "success")
        .scalar()
    )
    rows = (
        db.query(
            RequestLog.provider_used,
            func.avg(RequestLog.latency_ms).label("average_latency_ms"),
            func.min(RequestLog.latency_ms).label("min_latency_ms"),
            func.max(RequestLog.latency_ms).label("max_latency_ms"),
        )
        .filter(RequestLog.provider_used.isnot(None))
        .filter(RequestLog.request_status == "success")
        .group_by(RequestLog.provider_used)
        .all()
    )

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


def get_category_metrics(db: Session) -> dict:
    total_requests = db.query(func.count(RequestLog.id)).scalar() or 0
    rows = (
        db.query(
            RequestLog.request_category,
            func.count(RequestLog.id).label("total_requests"),
            func.sum(
                case((RequestLog.request_status == "success", 1), else_=0)
            ).label("successful_requests"),
        )
        .group_by(RequestLog.request_category)
        .all()
    )

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
    return queue_manager.snapshot()


def get_capacity_metrics() -> dict:
    return provider_capacity.snapshot()


def get_throughput_metrics(db: Session) -> dict:
    one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    recent_count = (
        db.query(func.count(RequestLog.id))
        .filter(RequestLog.created_at >= one_minute_ago)
        .scalar()
        or 0
    )
    completed_count = (
        db.query(func.count(RequestLog.id))
        .filter(RequestLog.lifecycle_state == "completed")
        .scalar()
        or 0
    )
    cancelled_count = (
        db.query(func.count(RequestLog.id))
        .filter(RequestLog.lifecycle_state == "cancelled")
        .scalar()
        or 0
    )
    avg_queue_wait = db.query(func.avg(RequestLog.queue_wait_ms)).scalar()
    avg_execution = db.query(func.avg(RequestLog.execution_duration_ms)).scalar()

    provider_rows = (
        db.query(
            RequestLog.provider_used,
            func.count(RequestLog.id).label("completed"),
        )
        .filter(RequestLog.lifecycle_state == "completed")
        .filter(RequestLog.provider_used.isnot(None))
        .group_by(RequestLog.provider_used)
        .all()
    )

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


def get_lifecycle_metrics(db: Session) -> dict:
    rows = (
        db.query(RequestLog.lifecycle_state, func.count(RequestLog.id))
        .group_by(RequestLog.lifecycle_state)
        .all()
    )
    priority_rows = (
        db.query(RequestLog.request_priority, func.count(RequestLog.id))
        .group_by(RequestLog.request_priority)
        .all()
    )
    return {
        "states": [
            {"state": state or "unknown", "count": count}
            for state, count in rows
        ],
        "priorities": [
            {"priority": priority or "unknown", "count": count}
            for priority, count in priority_rows
        ],
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
    return compute_orchestration_health()


def get_cost_metrics() -> dict:
    from app.services.cost_tracker import cost_tracker
    return cost_tracker.get_cost_summary()


def get_failover_metrics() -> dict:
    from app.services.failover_manager import failover_manager
    return failover_manager.snapshot()


def get_dedup_metrics() -> dict:
    from app.services.dedup_tracker import dedup_tracker
    return dedup_tracker.snapshot()

