from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_org
from app.auth.models import UserProfile
from app.database.session import get_db
from app.routes.schemas import CreateSessionRequest, SessionRequestItem, SessionSummary
from app.services.session_service import create_session, get_session_requests, list_sessions

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionSummary)
def create_operational_session(
    payload: CreateSessionRequest,
    user: UserProfile = Depends(require_org),
    db: Session = Depends(get_db),
) -> SessionSummary:
    session = create_session(db, title=payload.title, org_id=user.organization_id)
    return SessionSummary.model_validate(session, from_attributes=True)


@router.get("", response_model=list[SessionSummary])
def list_operational_sessions(
    page: int = 1,
    page_size: int = 40,
    user: UserProfile = Depends(require_org),
    db: Session = Depends(get_db)
) -> list[SessionSummary]:
    if page_size > 200:
        page_size = 200
    from app.models.inference_session import InferenceSession
    from app.services.session_service import cleanup_stale_sessions
    cleanup_stale_sessions(db, org_id=user.organization_id)
    offset = (page - 1) * page_size
    q = db.query(InferenceSession)
    if user.organization_id:
        q = q.filter(InferenceSession.organization_id == user.organization_id)
    sessions = q.order_by(InferenceSession.updated_at.desc()).offset(offset).limit(page_size).all()
    return [
        SessionSummary.model_validate(session, from_attributes=True)
        for session in sessions
    ]


@router.get("/{session_id}/requests", response_model=list[SessionRequestItem])
def get_operational_session_requests(
    session_id: str,
    user: UserProfile = Depends(require_org),
    db: Session = Depends(get_db),
) -> list[SessionRequestItem]:
    rows = get_session_requests(db, session_id, org_id=user.organization_id)
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
