"""Phase 10C — Auth Dependencies: Supabase JWT validation & RBAC enforcement.

These are FastAPI dependencies injected into protected route handlers.

Flow:
1. Frontend sends   Authorization: Bearer <supabase_jwt>
2. get_current_user() decodes & validates the JWT via Supabase public keys
3. It looks up the UserProfile in the local database
4. require_permission(perm) enforces RBAC on top of that user
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import AuditLog, UserProfile
from app.auth.rbac import has_permission
from app.database.session import get_db
from app.settings import settings

logger = logging.getLogger("qorvexis.auth")

# ── HTTP Bearer scheme ────────────────────────────────────────────────────────

bearer_scheme = HTTPBearer(auto_error=False)


# ── JWT validation ────────────────────────────────────────────────────────────

def _decode_supabase_jwt(token: str) -> dict:
    """Decode and validate a Supabase-issued JWT."""
    secret = getattr(settings, "supabase_jwt_secret", None)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: SUPABASE_JWT_SECRET is missing.",
        )

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
        )


# ── Core dependency ───────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserProfile:
    """Validate the Bearer JWT and return the requesting UserProfile.

    If the user profile doesn't exist yet in local DB we create a stub
    so that the first login works without a separate registration step.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_supabase_jwt(credentials.credentials)
    supabase_user_id: str | None = payload.get("sub")
    email: str | None = payload.get("email")

    if not supabase_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing user identity claim.",
        )

    # Load or create profile ──────────────────────────────────────────────────
    profile = db.query(UserProfile).filter_by(supabase_user_id=supabase_user_id).first()

    if not profile:
        # Auto-provision on first authenticated request
        profile = UserProfile(
            supabase_user_id=supabase_user_id,
            email=email or "",
            full_name=payload.get("user_metadata", {}).get("full_name"),
            role="Owner",  # First user defaults to Owner; admin can change later
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info("auth.user_provisioned supabase_id=%s email=%s", supabase_user_id, email)

    # Update last_login timestamp
    profile.last_login = datetime.utcnow()
    db.commit()

    return profile


# ── Optional dependency (returns None when unauthenticated) ───────────────────

def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserProfile | None:
    """Like get_current_user but returns None instead of raising 401."""
    if not credentials:
        return None
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


# ── RBAC guard factory ────────────────────────────────────────────────────────

def require_permission(permission: str) -> Callable:
    """Returns a FastAPI dependency that enforces a specific RBAC permission."""

    def _guard(user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. '{user.role}' role does not have '{permission}'.",
            )
        return user

    return _guard


def require_org(user: UserProfile = Depends(get_current_user)) -> UserProfile:
    """Ensure the user belongs to an active organization."""
    if not user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must belong to an organization to access this resource.",
        )
    return user


# ── Audit helper ──────────────────────────────────────────────────────────────

def log_audit(
    db: Session,
    user: UserProfile,
    action: str,
    target: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write an immutable audit log entry for a user action."""
    entry = AuditLog(
        organization_id=user.organization_id,
        user_id=user.supabase_user_id,
        action=action,
        target=target,
        event_metadata=json.dumps(metadata) if metadata else None,
    )
    db.add(entry)
    db.commit()
