from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.request_lifecycle_event import RequestLifecycleEvent
from app.models.request_log import RequestLog
from app.reliability.integrity import integrity_registry


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def get_request_timelines(db: Session, limit: int = 20) -> dict:
    rows = (
        db.query(RequestLog)
        .order_by(RequestLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "timelines": [
            {
                "request_id": row.id,
                "session_id": row.session_id,
                "provider": row.provider_used or row.original_provider,
                "lifecycle_state": row.lifecycle_state,
                "received_at": _iso(row.received_at or row.created_at),
                "queued_at": _iso(row.queued_at),
                "scheduled_at": _iso(row.scheduled_at),
                "execution_started_at": _iso(row.execution_started_at),
                "provider_response_at": _iso(row.provider_response_at),
                "completed_at": _iso(row.completed_at),
                "queue_wait_ms": row.queue_wait_ms,
                "execution_duration_ms": row.execution_duration_ms,
                "fallback_used": row.fallback_used,
                "cache_hit": row.cache_hit,
            }
            for row in rows
        ]
    }


def get_lifecycle_transition_view(db: Session, limit: int = 40) -> dict:
    rows = (
        db.query(RequestLifecycleEvent)
        .order_by(RequestLifecycleEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "transitions": [
            {
                "request_id": row.request_id,
                "state": row.state,
                "detail": row.detail,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


def detect_stale_requests(db: Session, stale_after_seconds: int = 300) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    rows = (
        db.query(RequestLog)
        .filter(RequestLog.lifecycle_state.in_(("queued", "scheduled", "executing", "fallback_executing")))
        .filter(RequestLog.created_at < cutoff)
        .order_by(RequestLog.created_at.asc())
        .limit(50)
        .all()
    )
    return [
        {
            "request_id": row.id,
            "state": row.lifecycle_state,
            "created_at": row.created_at.isoformat(),
            "provider": row.original_provider,
        }
        for row in rows
    ]


def get_diagnostics(db: Session) -> dict:
    from app.orchestration.queue_manager import queue_manager
    from app.services.response_cache import response_cache
    from app.services.failover_manager import failover_manager

    active_by_state = (
        db.query(RequestLog.lifecycle_state, func.count(RequestLog.id))
        .filter(RequestLog.lifecycle_state.in_(("queued", "scheduled", "executing", "fallback_executing")))
        .group_by(RequestLog.lifecycle_state)
        .all()
    )
    return {
        "queue": queue_manager.diagnostics(db),
        "active_lifecycle_states": [
            {"state": state, "count": count}
            for state, count in active_by_state
        ],
        "stale_requests": detect_stale_requests(db),
        "integrity": integrity_registry.snapshot(),
        "cache": response_cache.snapshot(),
        "provider_cooldowns": failover_manager.snapshot(),
        **get_request_timelines(db, limit=12),
        **get_lifecycle_transition_view(db, limit=20),
    }
