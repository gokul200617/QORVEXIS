"""Schemas for Token Intelligence."""

from datetime import datetime
from pydantic import BaseModel, Field

class TokenTelemetryCreate(BaseModel):
    organization_id: str | None = None
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    latency_ms: float = 0.0
    execution_duration_ms: float = 0.0
    request_category: str | None = None
    cache_hit: bool = False
    fallback_used: bool = False
    deduplicated: bool = False
    workload_signature: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    prompt_text: str | None = Field(default=None, description="Used for hashing and categorization, never stored permanently")

class TokenAnalyticsSummary(BaseModel):
    total_spend_usd: float
    estimated_monthly_usd: float
    total_requests: int
    most_expensive_model: str
    efficiency_score: float
    duplicate_workload_pct: float
    cache_opportunity_pct: float

class OptimizationRecommendationSchema(BaseModel):
    rule_id: str
    severity: str
    title: str
    detail: str
    estimated_monthly_waste_usd: float | None
    estimated_savings_usd: float | None
    created_at: datetime
