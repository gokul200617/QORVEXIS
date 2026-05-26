from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.inference_session import InferenceSession
from app.models.request_log import RequestLog

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
        if existing_session:
            return existing_session

    return create_session(db, title=build_session_title(prompt))


def touch_session(db: Session, session: InferenceSession) -> None:
    session.updated_at = datetime.now(timezone.utc)
    db.add(session)


def list_sessions(db: Session) -> list[InferenceSession]:
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
