from pydantic import BaseModel
from typing import Any

class GatewayChatRequest(BaseModel):
    provider:       str = "openai"         # openai | groq | gemini | openrouter
    model:          str = "gpt-4o-mini"
    messages:       list[dict[str, str]]
    
    # Provider overrides
    api_key:        str | None = None      # Optional if managed in Gateway DB
    temperature:    float = 0.7
    max_tokens:     int   = 1024
    stream:         bool  = False
    
    # Business attribution (All optional)
    team_id:        str | None = None
    team_name:      str | None = None
    customer_id:    str | None = None
    customer_name:  str | None = None
    workload_id:    str | None = None
    workload_name:  str | None = None
    application_id: str | None = None
    session_id:     str | None = None
    
    # Failover & Routing (Optional)
    fallback_provider: str | None = None
    fallback_model: str | None = None

class GatewayChatResponse(BaseModel):
    request_id:        str
    provider:          str
    model:             str
    content:           str
    prompt_tokens:     int
    completion_tokens: int
    total_tokens:      int
    estimated_cost:    float
    latency_ms:        float
    success:           bool
    error:             str | None = None
    fallback_used:     bool = False
