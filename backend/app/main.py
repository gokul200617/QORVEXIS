import logging
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401
from app.database.health import check_database, initialize_database
from app.orchestration.queue_manager import queue_manager
from app.routes.ask import router as ask_router
from app.routes.metrics import router as metrics_router
from app.routes.sessions import router as sessions_router
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ask_router)
    app.include_router(metrics_router)
    app.include_router(sessions_router)

    @app.on_event("startup")
    def ensure_database_tables() -> None:
        logger.info("api.startup.database_initialize")
        initialize_database()
        queue_manager.start()
        start_recovery_sweeper()

        # Phase 5 — initialize operational intelligence singletons
        from app.services.provider_scorer import provider_scorer  # noqa: F401
        from app.services.response_cache import response_cache  # noqa: F401
        from app.services.dedup_tracker import dedup_tracker  # noqa: F401
        from app.services.failover_manager import failover_manager  # noqa: F401
        from app.services.cost_tracker import cost_tracker  # noqa: F401
        logger.info("phase5.operational_intelligence.ready")
        logger.info("phase6.reliability_hardening.ready")

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
