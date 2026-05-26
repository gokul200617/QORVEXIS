from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.inference_session import InferenceSession
from app.models.request_log import RequestLog
from app.settings import settings

MEMORY_LIMIT = 6


def build_session_title(prompt: str) -> str:
    compact_prompt = " ".join(prompt.split())
    if not compact_prompt:
        return "Untitled session"
    return compact_prompt[:72]


def create_session(db: Session, title: str | None = None) -> InferenceSession:
    session = InferenceSession(title=title or "New operational session")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_or_create_session(
    db: Session,
    session_id: str | None,
    prompt: str,
) -> InferenceSession:
    if session_id:
        existing_session = (
            db.query(InferenceSession)
            .filter(InferenceSession.id == session_id)
            .one_or_none()
        )
        if existing_session and not is_session_stale(existing_session):
            return existing_session
        if existing_session:
            evict_session(db, existing_session.id)

    return create_session(db, title=build_session_title(prompt))


def touch_session(db: Session, session: InferenceSession) -> None:
    session.updated_at = datetime.now(timezone.utc)
    db.add(session)


def list_sessions(db: Session) -> list[InferenceSession]:
    cleanup_stale_sessions(db)
    return (
        db.query(InferenceSession)
        .order_by(InferenceSession.updated_at.desc())
        .limit(40)
        .all()
    )


def get_session_requests(db: Session, session_id: str) -> list[RequestLog]:
    return (
        db.query(RequestLog)
        .filter(RequestLog.session_id == session_id)
        .order_by(RequestLog.created_at.asc())
        .all()
    )


def get_recent_session_context(db: Session, session_id: str) -> list[dict[str, str]]:
    enforce_session_bounds(db, session_id)
    rows = (
        db.query(RequestLog)
        .filter(RequestLog.session_id == session_id)
        .filter(RequestLog.request_status == "success")
        .order_by(RequestLog.created_at.desc())
        .limit(MEMORY_LIMIT)
        .all()
    )

    return [
        {"prompt": row.prompt, "response": row.response}
        for row in reversed(rows)
    ]


def is_session_stale(session: InferenceSession) -> bool:
    ttl_cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.session_ttl_seconds)
    updated_at = session.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at < ttl_cutoff


def evict_session(db: Session, session_id: str) -> int:
    deleted_requests = (
        db.query(RequestLog)
        .filter(RequestLog.session_id == session_id)
        .delete(synchronize_session=False)
    )
    db.query(InferenceSession).filter(InferenceSession.id == session_id).delete(synchronize_session=False)
    db.commit()
    return deleted_requests


def cleanup_stale_sessions(db: Session) -> int:
    ttl_cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.session_ttl_seconds)
    stale_sessions = (
        db.query(InferenceSession)
        .filter(InferenceSession.updated_at < ttl_cutoff)
        .order_by(InferenceSession.updated_at.asc())
        .limit(settings.session_cleanup_batch_size)
        .all()
    )
    evicted = 0
    for session in stale_sessions:
        evicted += evict_session(db, session.id)
    return evicted


def enforce_session_bounds(db: Session, session_id: str) -> int:
    rows = (
        db.query(RequestLog.id)
        .filter(RequestLog.session_id == session_id)
        .order_by(RequestLog.created_at.desc())
        .offset(settings.session_max_requests)
        .all()
    )
    stale_ids = [row.id for row in rows]
    if not stale_ids:
        return 0
    deleted = (
        db.query(RequestLog)
        .filter(RequestLog.id.in_(stale_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def get_session_memory_metrics(db: Session) -> dict:
    cleanup_evictions = cleanup_stale_sessions(db)
    total_sessions = db.query(InferenceSession).count()
    total_session_requests = (
        db.query(RequestLog)
        .filter(RequestLog.session_id.isnot(None))
        .count()
    )
    return {
        "session_ttl_seconds": settings.session_ttl_seconds,
        "session_max_requests": settings.session_max_requests,
        "active_sessions": total_sessions,
        "session_backed_requests": total_session_requests,
        "cleanup_evictions": cleanup_evictions,
        "estimated_memory_items": min(total_session_requests, total_sessions * MEMORY_LIMIT),
    }
