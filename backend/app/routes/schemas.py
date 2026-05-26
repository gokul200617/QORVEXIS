from datetime import datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    session_id: str | None = None


class AskResponse(BaseModel):
    request_id: int
    session_id: str
    provider: str
    original_provider: str
    fallback_used: bool
    model: str
    category: str
    priority: str
    lifecycle_state: str
    queue_wait_ms: int
    execution_duration_ms: int
    response: str
    latency_ms: int
    cache_hit: bool = False
    deduplicated: bool = False
    estimated_cost: float | None = None


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SessionRequestItem(BaseModel):
    id: int
    prompt: str
    response: str
    provider: str | None
    model: str | None
    category: str | None
    status: str
    created_at: datetime
