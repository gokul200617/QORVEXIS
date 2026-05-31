import asyncio
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.settings import get_settings
from app.gateway.gateway_models import GatewayRequestRecord
from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
from app.auth.models import UserProfile

settings = get_settings()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def sync_gateway_records():
    db = SessionLocal()
    try:
        # Get user
        user = db.query(UserProfile).first()
        org_id = user.organization_id if user else "test-org"

        # Fetch records that haven't been synced (we will just take the latest for this demo)
        records = db.query(GatewayRequestRecord).all()
        
        count = 0
        for rec in records:
            # Check if it already exists
            exists = db.query(TokenTelemetryRecord).filter_by(request_id=rec.request_id).first()
            if not exists:
                telemetry = TokenTelemetryRecord(
                    organization_id=org_id,
                    provider=rec.provider,
                    model=rec.model,
                    prompt_tokens=rec.prompt_tokens,
                    completion_tokens=rec.completion_tokens,
                    total_tokens=rec.total_tokens,
                    estimated_cost=rec.estimated_cost,
                    latency_ms=rec.latency_ms,
                    execution_duration_ms=rec.latency_ms,
                    request_category=rec.workload_name or "API Gen",
                    workload_signature="sig_" + (rec.model or "unknown"),
                    session_id=rec.session_id,
                    request_id=rec.request_id,
                    completion_inflation_ratio=(rec.completion_tokens / max(1, rec.prompt_tokens)),
                    created_at=rec.created_at
                )
                db.add(telemetry)
                count += 1
        
        db.commit()
        print(f"Synced {count} records from AI Gateway to Business Intelligence Telemetry!")
        
    except Exception as e:
        db.rollback()
        print("Error:", e)
    finally:
        db.close()

if __name__ == "__main__":
    sync_gateway_records()
