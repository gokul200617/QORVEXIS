"""Connector management API — Phase 8A/8B/8D."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import log_audit, require_org
from app.auth.models import UserProfile
from app.connectors.base.connector_types import ConnectorType
from app.connectors.health.connector_health_service import connector_health_service
from app.connectors.registry.connector_registry import connector_registry
from app.connectors.schemas.connector_schema import ConnectorListResponse, ConnectorResponse
from app.connectors.schemas.connector_schema import ConnectorCreateRequest
from app.connectors.schemas.auth_schema import AuthConfigSchema, AuthType
from app.connectors.services.connector_service import connector_service
from app.database.session import Session, get_db

logger = logging.getLogger("qorvexis.routes.connectors")

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorResponse])
def list_connectors(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return all persisted connector instances."""
    return connector_service.list_connectors(db, org_id=user.organization_id)


@router.get("/health")
def get_connectors_health(user: UserProfile = Depends(require_org)):
    """Return in-memory health snapshots for all connectors."""
    return connector_health_service.snapshot()


@router.get("/status")
def get_connectors_status(user: UserProfile = Depends(require_org)):
    """Return high-level connector registry status."""
    return connector_registry.snapshot()


@router.get("/{connector_id}", response_model=ConnectorResponse)
def get_connector(connector_id: str, user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return details for a specific connector."""
    instance = connector_service.get_connector(db, connector_id, org_id=user.organization_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Connector not found")
    return instance


# ── OpenAI Specific Endpoints ─────────────────────────────────────────────────

class OpenAIAccountRequest(BaseModel):
    api_key: str
    name: str = "OpenAI Production"


@router.post("/openai/authenticate", response_model=ConnectorResponse)
def authenticate_openai(req: OpenAIAccountRequest, user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Authenticate and register a new OpenAI connector."""
    from app.connectors.openai.openai_connector import OpenAIConnector
    from app.connectors.services.connector_validation_service import connector_validation_service
    from app.connectors.services.ingestion_service import ingestion_service

    connector_id = f"openai-{int(datetime.now().timestamp())}"

    connector = OpenAIConnector(
        connector_id=connector_id,
        name=req.name,
        api_key=req.api_key,
    )

    passed = connector_validation_service.validate(connector)
    if not passed:
        raise HTTPException(status_code=401, detail="Invalid OpenAI API Key")

    connector_registry.register(connector)

    masked = f"sk-...{req.api_key[-4:]}" if len(req.api_key) > 4 else "sk-...xxxx"
    create_req = ConnectorCreateRequest(
        connector_id=connector_id,
        name=req.name,
        connector_type=ConnectorType.AI_PROVIDER,
        description="Auto-registered OpenAI connection",
        auth_config=AuthConfigSchema(
            auth_type=AuthType.API_KEY,
            masked_identifier=masked,
        ),
    )
    instance = connector_service.create_connector(db, create_req, org_id=user.organization_id)
    ingestion_service.run_sync(db, connector, org_id=user.organization_id)
    log_audit(db, user, "provider.added", target="openai", metadata={"connector_id": connector_id})
    return instance


@router.get("/openai/usage")
def get_openai_usage(user: UserProfile = Depends(require_org)):
    """Return aggregated token analytics for the dashboard."""
    from app.connectors.openai.openai_usage_service import openai_usage_service
    return openai_usage_service.get_analytics_summary(org_id=user.organization_id)


# ── AWS Infrastructure Intelligence Endpoints — Phase 8D ─────────────────────

class AWSConnectRequest(BaseModel):
    access_key:      str
    secret_key:      str
    region:          str = "us-east-1"
    name:            str = "AWS Production"
    simulation_mode: bool = False


@router.post("/aws/connect")
def connect_aws(req: AWSConnectRequest, user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    try:
        from app.connectors.aws.aws_connector import AWSConnector
        from app.connectors.services.connector_validation_service import connector_validation_service
        from app.connectors.services.ingestion_service import ingestion_service

        connector_id = f"aws-{req.region}-{int(datetime.now().timestamp())}"

        connector = AWSConnector(
            connector_id=connector_id,
            name=req.name,
            access_key=req.access_key,
            secret_key=req.secret_key,
            region=req.region,
            simulation_mode=req.simulation_mode,
        )

        passed = connector_validation_service.validate(connector)
        if not passed and not req.simulation_mode:
            raise HTTPException(
                status_code=401,
                detail="Invalid AWS credentials. Verify your Access Key ID and Secret Access Key.",
            )

        connector_registry.register(connector)

        masked_key = connector.connector_id
        if len(req.access_key) > 8:
            masked_key = f"AKIA...{req.access_key[-4:]}"

        create_req = ConnectorCreateRequest(
            connector_id=connector_id,
            name=req.name,
            connector_type=ConnectorType.CLOUD_PROVIDER,
            description=f"AWS account connector — region: {req.region}"
                        + (" [DEMO]" if req.simulation_mode else ""),
            auth_config=AuthConfigSchema(
                auth_type=AuthType.IAM_ROLE,
                masked_identifier=masked_key,
            ),
        )
        instance = connector_service.create_connector(db, create_req, org_id=user.organization_id)

        try:
            ingestion_service.run_sync(db, connector, org_id=user.organization_id)
        except Exception as sync_exc:
            logger.warning("aws.connect.initial_sync_failed detail=%s", sync_exc)

        return {
            "connector_id":   connector_id,
            "name":           req.name,
            "region":         req.region,
            "simulation_mode": req.simulation_mode,
            "status":         "connected",
            "message":        "AWS connector registered successfully."
                              if not req.simulation_mode
                              else "AWS connector registered in demo mode.",
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("aws.connect.error detail=%s", exc)
        raise HTTPException(status_code=500, detail=f"AWS connector registration failed: {exc}")


@router.get("/aws/health")
def get_aws_health(user: UserProfile = Depends(require_org)):
    try:
        from app.connectors.aws.aws_usage_service import aws_usage_service
        return aws_usage_service.get_health()
    except Exception as exc:
        logger.warning("aws.health.error detail=%s", exc)
        return {"available": False, "reason": f"AWS health check unavailable: {exc}"}


@router.get("/aws/infrastructure")
def get_aws_infrastructure(user: UserProfile = Depends(require_org)):
    try:
        from app.connectors.aws.aws_usage_service import aws_usage_service
        return aws_usage_service.get_infrastructure_summary(org_id=user.organization_id)
    except Exception as exc:
        logger.warning("aws.infrastructure.error detail=%s", exc)
        return {"available": False, "reason": f"AWS infrastructure data unavailable: {exc}", "instances": [], "total_instances": 0, "running_instances": 0}


@router.get("/aws/costs")
def get_aws_costs(user: UserProfile = Depends(require_org)):
    try:
        from app.connectors.aws.aws_usage_service import aws_usage_service
        return aws_usage_service.get_cost_summary(org_id=user.organization_id)
    except Exception as exc:
        logger.warning("aws.costs.error detail=%s", exc)
        return {"available": False, "reason": f"AWS cost data unavailable: {exc}", "monthly_spend": 0.0, "daily_spend": 0.0}


@router.get("/aws/recommendations")
def get_aws_recommendations(user: UserProfile = Depends(require_org)):
    try:
        from app.connectors.aws.aws_usage_service import aws_usage_service
        return aws_usage_service.get_recommendations(org_id=user.organization_id)
    except Exception as exc:
        logger.warning("aws.recommendations.error detail=%s", exc)
        return {"available": False, "reason": f"AWS recommendations unavailable: {exc}", "recommendations": [], "recommendation_count": 0}


@router.get("/aws/summary")
def get_aws_summary(user: UserProfile = Depends(require_org)):
    try:
        from app.connectors.aws.aws_connector_summary_service import aws_connector_summary_service
        return aws_connector_summary_service.get_summary(org_id=user.organization_id)
    except Exception as exc:
        logger.warning("aws.summary.error detail=%s", exc)
        return {
            "monthly_spend": 0.0,
            "daily_spend": 0.0,
            "active_instances": 0,
            "total_instances": 0,
            "underutilized_instances": 0,
            "estimated_savings": 0.0,
            "infrastructure_health_score": 0.0,
            "optimization_score": 0.0,
            "waste_score": 0.0,
            "connector_status": "error",
            "last_sync": None,
            "available": False,
            "reason": f"AWS summary unavailable: {exc}",
        }


# ── Groq & Gemini Intelligence Endpoints — Phase 9 ───────────────────────────

class GroqConnectRequest(BaseModel):
    api_key: str
    name: str = "Groq Production"
    simulation_mode: bool = False

@router.post("/groq/connect", response_model=ConnectorResponse)
def connect_groq(req: GroqConnectRequest, user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    try:
        from app.connectors.groq.groq_connector import GroqConnector
        from app.connectors.services.connector_validation_service import connector_validation_service

        connector_id = f"groq-{int(datetime.now().timestamp())}"

        connector = GroqConnector(
            connector_id=connector_id,
            name=req.name,
            api_key=req.api_key,
            simulation_mode=req.simulation_mode,
        )

        passed = connector_validation_service.validate(connector)
        if not passed and not req.simulation_mode:
            raise HTTPException(status_code=401, detail="Invalid Groq API Key.")

        connector_registry.register(connector)

        masked = f"gsk-...{req.api_key[-4:]}" if len(req.api_key) > 4 else "gsk-...xxxx"
        create_req = ConnectorCreateRequest(
            connector_id=connector_id,
            name=req.name,
            connector_type=ConnectorType.AI_PROVIDER,
            description="Groq connection",
            auth_config=AuthConfigSchema(
                auth_type=AuthType.API_KEY,
                masked_identifier=masked,
            ),
        )
        return connector_service.create_connector(db, create_req, org_id=user.organization_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("groq.connect.error detail=%s", exc)
        raise HTTPException(status_code=500, detail=f"Groq registration failed: {exc}")


class GeminiConnectRequest(BaseModel):
    api_key: str
    name: str = "Gemini Production"
    simulation_mode: bool = False

@router.post("/gemini/connect", response_model=ConnectorResponse)
def connect_gemini(req: GeminiConnectRequest, user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    try:
        from app.connectors.gemini.gemini_connector import GeminiConnector
        from app.connectors.services.connector_validation_service import connector_validation_service

        connector_id = f"gemini-{int(datetime.now().timestamp())}"

        connector = GeminiConnector(
            connector_id=connector_id,
            name=req.name,
            api_key=req.api_key,
            simulation_mode=req.simulation_mode,
        )

        passed = connector_validation_service.validate(connector)
        if not passed and not req.simulation_mode:
            raise HTTPException(status_code=401, detail="Invalid Gemini API Key.")

        connector_registry.register(connector)

        masked = f"AIz-...{req.api_key[-4:]}" if len(req.api_key) > 4 else "AIz-...xxxx"
        create_req = ConnectorCreateRequest(
            connector_id=connector_id,
            name=req.name,
            connector_type=ConnectorType.AI_PROVIDER,
            description="Gemini connection",
            auth_config=AuthConfigSchema(
                auth_type=AuthType.API_KEY,
                masked_identifier=masked,
            ),
        )
        return connector_service.create_connector(db, create_req, org_id=user.organization_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("gemini.connect.error detail=%s", exc)
        raise HTTPException(status_code=500, detail=f"Gemini registration failed: {exc}")


class OpenRouterConnectRequest(BaseModel):
    api_key: str
    name: str = "OpenRouter Production"
    simulation_mode: bool = False

@router.post("/openrouter/connect", response_model=ConnectorResponse)
def connect_openrouter(req: OpenRouterConnectRequest, user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    try:
        from app.connectors.openrouter.openrouter_connector import OpenRouterConnector
        from app.connectors.services.connector_validation_service import connector_validation_service

        connector_id = f"openrouter-{int(datetime.now().timestamp())}"

        connector = OpenRouterConnector(
            connector_id=connector_id,
            name=req.name,
            api_key=req.api_key,
            simulation_mode=req.simulation_mode,
        )

        passed = connector_validation_service.validate(connector)
        if not passed and not req.simulation_mode:
            raise HTTPException(status_code=401, detail="Invalid OpenRouter API Key.")

        connector_registry.register(connector)

        masked = f"sk-or-v1-...{req.api_key[-4:]}" if len(req.api_key) > 4 else "sk-or-v1-...xxxx"
        create_req = ConnectorCreateRequest(
            connector_id=connector_id,
            name=req.name,
            connector_type=ConnectorType.AI_PROVIDER,
            description="OpenRouter connection",
            auth_config=AuthConfigSchema(
                auth_type=AuthType.API_KEY,
                masked_identifier=masked,
            ),
        )
        return connector_service.create_connector(db, create_req, org_id=user.organization_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("openrouter.connect.error detail=%s", exc)
        raise HTTPException(status_code=500, detail=f"OpenRouter registration failed: {exc}")
