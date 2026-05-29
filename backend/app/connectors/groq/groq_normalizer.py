"""Provider-specific normalizer for Groq telemetry."""

from app.connectors.normalization.normalization_engine import normalization_engine
from app.connectors.normalization.normalized_models import NormalizedProviderTelemetry


def transform_groq_usage(raw: dict) -> list[NormalizedProviderTelemetry]:
    """Transform Groq usage records (simulated or raw) into Qorvexis normalized models."""
    
    records = raw.get("data", [])
    if not records:
        return []

    telemetry_list = []
    
    for r in records:
        prompt = r.get("n_context_tokens_total", 0)
        completion = r.get("n_generated_tokens_total", 0)
        model = r.get("snapshot_id", "default")
        requests = r.get("n_requests", 0)
        latency = r.get("estimated_latency_ms", 300.0)
        
        # Groq is roughly $0.0007 / 1K tokens for Llama-3-70b
        cost_per_token = 0.0000007
        estimated_cost = (prompt + completion) * cost_per_token
        
        telemetry_list.append(NormalizedProviderTelemetry(
            provider="groq",
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            latency=float(latency),
            estimated_cost=estimated_cost,
            request_count=requests,
        ))

    return telemetry_list

# Note: We won't register this with the Phase 8 normalization_engine if it
# expects NormalizedTelemetry. This acts as a utility mapping for Phase 9.
