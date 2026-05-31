from fastapi import APIRouter, Depends, HTTPException
from typing import Any
import logging

from app.auth.dependencies import require_org
from app.auth.models import UserProfile
from app.gateway.gateway_schemas import GatewayChatRequest, GatewayChatResponse
from app.gateway.gateway_service import gateway_service
from app.gateway.gateway_provider_registry import gateway_provider_registry

logger = logging.getLogger("qorvexis.gateway.router")
router = APIRouter(prefix="/gateway", tags=["gateway"])

@router.post("/chat", response_model=GatewayChatResponse)
def gateway_chat(req: GatewayChatRequest, user: UserProfile = Depends(require_org)) -> GatewayChatResponse:
    """
    Proxy a chat completion through Qorvexis, capturing full business attribution telemetry.
    """
    if req.provider not in gateway_provider_registry.list_providers():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{req.provider}'. Supported: {gateway_provider_registry.list_providers()}",
        )

    # We attach org_id to the request dict or pass it via kwargs if possible,
    # or just assume gateway_service.execute accepts it. We'll pass it to execute.
    result = gateway_service.execute(req, org_id=user.organization_id)
    
    if not result.success:
        raise HTTPException(
            status_code=502,
            detail=f"Gateway proxy failed: {result.error}"
        )
        
    return result

@router.post("/completions", response_model=GatewayChatResponse)
def gateway_completions(req: GatewayChatRequest, user: UserProfile = Depends(require_org)) -> GatewayChatResponse:
    """Alias for /chat, preserving OpenAI compatibility."""
    return gateway_chat(req, user)

@router.get("/health")
def gateway_health(user: UserProfile = Depends(require_org)) -> dict:
    """Returns gateway service availability."""
    return {
        "status": "ok", 
        "service": "qorvexis-gateway", 
        "supported_providers": gateway_provider_registry.list_providers()
    }

@router.get("/providers")
def gateway_providers(user: UserProfile = Depends(require_org)) -> list[str]:
    """Returns supported gateway providers."""
    return gateway_provider_registry.list_providers()

from pydantic import BaseModel
class AddCredentialRequest(BaseModel):
    provider: str
    api_key: str

@router.post("/credentials")
def add_gateway_credential(req: AddCredentialRequest, user: UserProfile = Depends(require_org)):
    """Securely add an API key for the AI Gateway to use."""
    from app.database.session import SessionLocal
    from app.gateway.provider_credentials.credential_manager import credential_manager
    
    with SessionLocal() as db:
        cred = credential_manager.add_credential(db, req.provider, req.api_key, org_id=user.organization_id)
        return {"status": "success", "provider": cred.provider, "masked_key": cred.masked_key}
