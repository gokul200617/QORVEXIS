"""Pydantic schemas for OpenAI Usage API responses."""

from datetime import datetime
from pydantic import BaseModel, Field


class OpenAIUsageRecord(BaseModel):
    """Represents a single usage datapoint from OpenAI."""
    timestamp: int
    n_requests: int
    operation: str
    organization_id: str
    snapshot_id: str
    n_context_tokens_total: int
    n_generated_tokens_total: int


class OpenAIUsageResponse(BaseModel):
    """Represents the paginated usage response from OpenAI."""
    data: list[OpenAIUsageRecord]
    has_more: bool
    next_page: str | None = None


class OpenAIAuthValidateResponse(BaseModel):
    """Represents a basic models list response used to validate keys."""
    data: list[dict]
    object: str
