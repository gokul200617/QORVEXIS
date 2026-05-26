from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.routes.schemas import CreateSessionRequest, SessionRequestItem, SessionSummary
from app.services.session_service import create_session, get_session_requests, list_sessions

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionSummary)
def create_operational_session(
    payload: CreateSessionRequest,
    db: Session = Depends(get_db),
) -> SessionSummary:
    session = create_session(db, title=payload.title)
    return SessionSummary.model_validate(session, from_attributes=True)


@router.get("", response_model=list[SessionSummary])
def list_operational_sessions(db: Session = Depends(get_db)) -> list[SessionSummary]:
    return [
        SessionSummary.model_validate(session, from_attributes=True)
        for session in list_sessions(db)
    ]


@router.get("/{session_id}/requests", response_model=list[SessionRequestItem])
def get_operational_session_requests(
    session_id: str,
    db: Session = Depends(get_db),
) -> list[SessionRequestItem]:
    rows = get_session_requests(db, session_id)
    if not rows:
        return []

    return [
        SessionRequestItem(
            id=row.id,
            prompt=row.prompt,
            response=row.response,
            provider=row.provider_used,
            model=row.model_used,
            category=row.request_category,
            status=row.request_status,
            created_at=row.created_at,
        )
        for row in rows
    ]
