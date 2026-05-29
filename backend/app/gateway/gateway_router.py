from fastapi import APIRouter, HTTPException
from typing import Any
import logging

from app.gateway.gateway_schemas import GatewayChatRequest, GatewayChatResponse
from app.gateway.gateway_service import gateway_service
from app.gateway.gateway_provider_registry import gateway_provider_registry

logger = logging.getLogger("qorvexis.gateway.router")
router = APIRouter(prefix="/gateway", tags=["gateway"])

@router.post("/chat", response_model=GatewayChatResponse)
def gateway_chat(req: GatewayChatRequest) -> GatewayChatResponse:
    """
    Proxy a chat completion through Qorvexis, capturing full business attribution telemetry.
    """
    if req.provider not in gateway_provider_registry.list_providers():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{req.provider}'. Supported: {gateway_provider_registry.list_providers()}",
        )

    result = gateway_service.execute(req)
    
    if not result.success:
        # We can either return 502 or 200 with success=False.
        # The prompt specifies returning a GatewayChatResponse for standard use.
        raise HTTPException(
            status_code=502,
            detail=f"Gateway proxy failed: {result.error}"
        )
        
    return result

@router.post("/completions", response_model=GatewayChatResponse)
def gateway_completions(req: GatewayChatRequest) -> GatewayChatResponse:
    """Alias for /chat, preserving OpenAI compatibility."""
    return gateway_chat(req)

@router.get("/health")
def gateway_health() -> dict:
    """Returns gateway service availability."""
    return {
        "status": "ok", 
        "service": "qorvexis-gateway", 
        "supported_providers": gateway_provider_registry.list_providers()
    }

@router.get("/providers")
def gateway_providers() -> list[str]:
    """Returns supported gateway providers."""
    return gateway_provider_registry.list_providers()

from pydantic import BaseModel
class AddCredentialRequest(BaseModel):
    provider: str
    api_key: str

@router.post("/credentials")
def add_gateway_credential(req: AddCredentialRequest):
    """Securely add an API key for the AI Gateway to use."""
    from app.database.session import SessionLocal
    from app.gateway.provider_credentials.credential_manager import credential_manager
    
    with SessionLocal() as db:
        cred = credential_manager.add_credential(db, req.provider, req.api_key)
        return {"status": "success", "provider": cred.provider, "masked_key": cred.masked_key}
