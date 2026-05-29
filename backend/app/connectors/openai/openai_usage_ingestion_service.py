"""Phase 10A — OpenAI Usage Ingestion Service.

Orchestrates the ingestion of historical usage from OpenAI and persists
it as a ProviderUsageSnapshot. Uses GatewayCostEngine to estimate cost.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.connectors.openai.openai_usage_provider import OpenAIUsageProvider
from app.connectors.models.provider_usage_snapshot import ProviderUsageSnapshot
from app.connectors.base.provider_capabilities import ProviderDataSource, ProviderDataConfidence
from app.gateway.gateway_cost_engine import gateway_cost_engine

logger = logging.getLogger("qorvexis.connectors.openai.ingestion")


class OpenAIUsageIngestionService:

    def ingest_daily_usage(self, db: Session, api_key: str, target_date: datetime | None = None) -> ProviderUsageSnapshot:
        """Fetches usage for target_date (defaults to yesterday) and persists snapshot."""
        if target_date is None:
            target_date = datetime.now(timezone.utc) - timedelta(days=1)
        
        # Normalize target date to midnight UTC for the snapshot timestamp
        snapshot_time = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

        provider = OpenAIUsageProvider(api_key)
        data = provider.fetch_daily_usage(target_date)

        # Estimate cost based on the exact models used
        estimated_cost = 0.0
        # Since the usage endpoint provides aggregate tokens but not split by prompt/completion per model 
        # in the simple response, we use an average blend or just use the gateway cost engine for the 'default' model
        # if specific token split is unknown. Wait, our cost engine needs prompt/completion split.
        # We know total prompt and completion for the day, but not per-model strictly from the basic endpoint.
        # For precise costing, we can approximate based on the ratio.
        prompt_ratio = data["prompt_tokens"] / max(data["total_tokens"], 1)
        completion_ratio = data["completion_tokens"] / max(data["total_tokens"], 1)

        for model_name, model_tokens in data["model_distribution"].items():
            m_prompt = int(model_tokens * prompt_ratio)
            m_comp = int(model_tokens * completion_ratio)
            estimated_cost += gateway_cost_engine.estimate("openai", model_name, m_prompt, m_comp)

        # Upsert logic (replace if exists for this day)
        existing = db.query(ProviderUsageSnapshot).filter(
            ProviderUsageSnapshot.provider == "openai",
            ProviderUsageSnapshot.timestamp == snapshot_time,
            ProviderUsageSnapshot.source == ProviderDataSource.PROVIDER_API.value
        ).first()

        if existing:
            existing.requests = data["requests"]
            existing.prompt_tokens = data["prompt_tokens"]
            existing.completion_tokens = data["completion_tokens"]
            existing.total_tokens = data["total_tokens"]
            existing.estimated_cost = estimated_cost
            existing.model_distribution = data["model_distribution"]
            record = existing
        else:
            record = ProviderUsageSnapshot(
                provider="openai",
                timestamp=snapshot_time,
                requests=data["requests"],
                prompt_tokens=data["prompt_tokens"],
                completion_tokens=data["completion_tokens"],
                total_tokens=data["total_tokens"],
                estimated_cost=estimated_cost,
                model_distribution=data["model_distribution"],
                source=ProviderDataSource.PROVIDER_API.value,
                confidence=ProviderDataConfidence.REAL_PROVIDER_USAGE.value,
            )
            db.add(record)

        db.commit()
        db.refresh(record)
        
        logger.info("sync.snapshot.created provider=openai tokens=%d cost=%.4f", record.total_tokens, record.estimated_cost)
        return record


openai_usage_ingestion_service = OpenAIUsageIngestionService()
