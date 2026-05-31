import logging
import threading
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app import models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401 — Phase 10C: register auth tables
from app.database.health import check_database, initialize_database
from app.orchestration.queue_manager import queue_manager
from app.routes.ask import router as ask_router
from app.routes.metrics import router as metrics_router
from app.routes.sessions import router as sessions_router
from app.routes.telemetry import router as telemetry_router
from app.routes.connectors import router as connectors_router
from app.routes.token_analytics import router as token_analytics_router
from app.security.headers_middleware import SecurityHeadersMiddleware
from app.security.rate_limiter import limiter
from app.settings import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("qorvexis.api")


def start_recovery_sweeper() -> None:
    from app.reliability.recovery import sweep_stale_executions

    def run() -> None:
        while True:
            try:
                sweep_stale_executions()
            except Exception as exc:
                logger.warning("recovery.sweep_failed error=%s", exc)
            time.sleep(60)

    thread = threading.Thread(target=run, name="qorvexis-recovery-sweeper", daemon=True)
    thread.start()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Foundational API for the Qorvexis infrastructure platform.",
    )

    # ── Phase 10D: Security headers on every response ────────────────────────
    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Phase 10D: Rate limiter state attached to app ────────────────────────
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "detail": f"Too many requests. Limit: {exc.detail}. Please slow down.",
            },
            headers={"Retry-After": "60"},
        )

    from fastapi import Depends
    from app.auth.dependencies import require_org

    app.include_router(ask_router, dependencies=[Depends(require_org)])
    app.include_router(metrics_router, dependencies=[Depends(require_org)])
    app.include_router(sessions_router, dependencies=[Depends(require_org)])
    app.include_router(telemetry_router, dependencies=[Depends(require_org)])
    app.include_router(connectors_router, dependencies=[Depends(require_org)])
    app.include_router(token_analytics_router, dependencies=[Depends(require_org)])

    from app.routes.providers import router as providers_router
    app.include_router(providers_router, dependencies=[Depends(require_org)])

    from app.gateway.gateway_router import router as gateway_router
    app.include_router(gateway_router, dependencies=[Depends(require_org)])

    from app.routes.business import router as business_router
    app.include_router(business_router, dependencies=[Depends(require_org)])

    from app.auth.routes import router as auth_router  # Phase 10C
    app.include_router(auth_router)

    @app.on_event("startup")
    def ensure_database_tables() -> None:
        logger.info("api.startup.database_initialize")
        initialize_database()
        queue_manager.start()
        start_recovery_sweeper()

        # Phase 10D: Validate credential encryption key is set
        if not settings.credential_encryption_key:
            logger.warning(
                "security.credential_encryption_key.MISSING — "
                "Provider credentials will NOT be encrypted at rest. "
                "Set CREDENTIAL_ENCRYPTION_KEY in .env to enable encryption."
            )

        # Phase 5 — initialize operational intelligence singletons
        from app.services.provider_scorer import provider_scorer  # noqa: F401
        from app.services.response_cache import response_cache  # noqa: F401
        from app.services.dedup_tracker import dedup_tracker  # noqa: F401
        from app.services.failover_manager import failover_manager  # noqa: F401
        from app.services.cost_tracker import cost_tracker  # noqa: F401
        logger.info("phase5.operational_intelligence.ready")
        logger.info("phase6.reliability_hardening.ready")

        # Phase 7 — Initialize telemetry provider
        from app.telemetry.providers.telemetry_provider import telemetry_provider  # noqa: F401
        logger.info("phase7.infrastructure_telemetry.ready")

        # Phase 8A — Initialize connector framework registry
        from app.connectors.registry.connector_registry import connector_registry  # noqa: F401
        logger.info("phase8a.connector_framework.ready")

        # Phase 8D — Initialize AWS Infrastructure Intelligence connector services
        from app.connectors.aws.aws_usage_service import aws_usage_service  # noqa: F401
        from app.connectors.aws.aws_connector_summary_service import aws_connector_summary_service  # noqa: F401
        logger.info("phase8d.aws_infrastructure_intelligence.ready")

        # Phase 9 — Multi-Provider Intelligence
        from app.connectors.services.provider_intelligence_service import provider_intelligence_service  # noqa: F401
        logger.info("phase9.multi_provider_intelligence.ready")

        # Phase 10 — AI Gateway & Business Intelligence
        from app.gateway.gateway_telemetry import gateway_telemetry  # noqa: F401
        from app.business.business_intelligence_service import business_intelligence_service  # noqa: F401
        logger.info("phase10.ai_gateway.business_intelligence.ready")

        logger.info("phase10d.security_hardening.ready")

    @app.get("/health")
    def health_check() -> dict[str, str | None]:
        database_ok, database_error = check_database()
        return {
            "status": "ok" if database_ok else "degraded",
            "service": settings.app_name,
            "database": "connected" if database_ok else "unavailable",
            "database_error": database_error,
        }

    return app


app = create_app()
