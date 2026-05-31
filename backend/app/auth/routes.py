"""Phase 10C — Auth API Routes.

Endpoints:
  POST /auth/profile          → Get or create user profile
  GET  /auth/me               → Return current user & permissions
  POST /auth/org              → Create an organization (onboarding)
  GET  /auth/org              → Get current org info
  POST /auth/org/invite       → Invite a new member (stub — sends no real email yet)
  GET  /auth/org/members      → List all members
  PATCH /auth/org/members/{uid}/role  → Change a member's role
  DELETE /auth/org/members/{uid}      → Remove a member
  GET  /auth/audit            → List audit logs (Owner/Admin only)
  GET  /auth/teams            → List teams
  POST /auth/teams            → Create a team
"""

import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, log_audit, require_permission
from app.auth.models import AuditLog, Organization, Team, UserProfile
from app.auth.rbac import get_permissions
from app.database.session import get_db

logger = logging.getLogger("qorvexis.routes.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class MeResponse(BaseModel):
    id: str
    supabase_user_id: str
    email: str
    full_name: Optional[str]
    role: str
    organization_id: Optional[str]
    avatar_url: Optional[str]
    permissions: list[str]

    class Config:
        from_attributes = True


class OrgCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    owner_user_id: Optional[str]
    subscription_plan: str
    status: str

    class Config:
        from_attributes = True


class InviteRequest(BaseModel):
    email: str
    role: str = "Viewer"


class RoleChangeRequest(BaseModel):
    role: str


class TeamCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


class TeamResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    description: Optional[str]

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_ROLES = {"Owner", "Admin", "Manager", "Engineer", "Finance", "Viewer"}


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug[:64].strip("-")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=MeResponse)
def get_me(
    user: UserProfile = Depends(get_current_user),
):
    """Return the authenticated user's profile and full permission set."""
    return {
        "id": user.id,
        "supabase_user_id": user.supabase_user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "organization_id": user.organization_id,
        "avatar_url": user.avatar_url,
        "permissions": sorted(get_permissions(user.role)),
    }


@router.post("/org", response_model=OrgResponse, status_code=201)
def create_organization(
    req: OrgCreateRequest,
    user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new organization and assign the creating user as Owner."""
    if user.organization_id:
        raise HTTPException(
            status_code=400,
            detail="You already belong to an organization. Leave it before creating a new one.",
        )

    slug = req.slug or _slugify(req.name)
    # Ensure slug is unique
    existing = db.query(Organization).filter_by(slug=slug).first()
    if existing:
        slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

    org = Organization(
        name=req.name,
        slug=slug,
        owner_user_id=user.supabase_user_id,
    )
    db.add(org)
    db.flush()  # Populate org.id

    user.organization_id = org.id
    user.role = "Owner"
    db.commit()
    db.refresh(org)

    log_audit(db, user, "org.created", target=org.id, metadata={"name": org.name})
    logger.info("auth.org_created org_id=%s by=%s", org.id, user.supabase_user_id)
    return org


@router.get("/org", response_model=OrgResponse)
def get_organization(
    user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current user's organization."""
    if not user.organization_id:
        raise HTTPException(status_code=404, detail="No organization found.")
    org = db.query(Organization).filter_by(id=user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return org


@router.get("/org/members")
def list_members(
    user: UserProfile = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    """List all members of the current organization."""
    members = db.query(UserProfile).filter_by(organization_id=user.organization_id).all()
    return [
        {
            "id": m.id,
            "supabase_user_id": m.supabase_user_id,
            "email": m.email,
            "full_name": m.full_name,
            "role": m.role,
            "last_login": m.last_login.isoformat() if m.last_login else None,
        }
        for m in members
    ]


@router.patch("/org/members/{supabase_uid}/role")
def change_member_role(
    supabase_uid: str,
    req: RoleChangeRequest,
    user: UserProfile = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    """Change another member's role (Admin/Owner only)."""
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {sorted(VALID_ROLES)}")

    # Cannot grant Owner unless you are Owner
    if req.role == "Owner" and user.role != "Owner":
        raise HTTPException(status_code=403, detail="Only an Owner can grant the Owner role.")

    target = (
        db.query(UserProfile)
        .filter_by(supabase_user_id=supabase_uid, organization_id=user.organization_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Member not found.")

    old_role = target.role
    target.role = req.role
    db.commit()

    log_audit(db, user, "role.changed", target=supabase_uid, metadata={"from": old_role, "to": req.role})
    return {"message": f"Role updated to '{req.role}'.", "user_id": supabase_uid}


@router.delete("/org/members/{supabase_uid}")
def remove_member(
    supabase_uid: str,
    user: UserProfile = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    """Remove a member from the organization."""
    target = (
        db.query(UserProfile)
        .filter_by(supabase_user_id=supabase_uid, organization_id=user.organization_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Member not found.")
    if target.role == "Owner":
        raise HTTPException(status_code=403, detail="Cannot remove the organization Owner.")

    target.organization_id = None
    target.role = "Viewer"
    db.commit()

    log_audit(db, user, "member.removed", target=supabase_uid)
    return {"message": "Member removed from organization."}


@router.post("/org/invite")
def invite_member(
    req: InviteRequest,
    user: UserProfile = Depends(require_permission("can_manage_users")),
):
    """Invite a new member to the organization.

    In a production system this would send an email via Supabase Auth inviteUserByEmail().
    This endpoint documents the intent and returns the invite payload for the frontend.
    """
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {sorted(VALID_ROLES)}")

    return {
        "message": f"Invitation queued for {req.email} with role '{req.role}'.",
        "note": "Configure SUPABASE_SERVICE_KEY to enable automated email delivery.",
        "email": req.email,
        "role": req.role,
        "org_id": user.organization_id,
    }


@router.get("/audit")
def get_audit_logs(
    limit: int = 50,
    user: UserProfile = Depends(require_permission("can_view_audit_logs")),
    db: Session = Depends(get_db),
):
    """Return audit logs for the current organization."""
    logs = (
        db.query(AuditLog)
        .filter_by(organization_id=user.organization_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": l.id,
            "user_id": l.user_id,
            "action": l.action,
            "target": l.target,
            "metadata": l.event_metadata,
            "timestamp": l.timestamp.isoformat(),
        }
        for l in logs
    ]


@router.get("/teams", response_model=list[TeamResponse])
def list_teams(
    user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List teams in the current organization."""
    if not user.organization_id:
        return []
    return db.query(Team).filter_by(organization_id=user.organization_id).all()


@router.post("/teams", response_model=TeamResponse, status_code=201)
def create_team(
    req: TeamCreateRequest,
    user: UserProfile = Depends(require_permission("can_manage_teams")),
    db: Session = Depends(get_db),
):
    """Create a new team in the current organization."""
    team = Team(
        organization_id=user.organization_id,
        name=req.name,
        description=req.description,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    log_audit(db, user, "team.created", target=team.id, metadata={"name": team.name})
    return team
