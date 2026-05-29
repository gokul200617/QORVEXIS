"""Provider-specific normalizer for OpenRouter telemetry."""

from app.connectors.normalization.normalized_models import NormalizedProviderTelemetry


def transform_openrouter_usage(raw: dict) -> list[NormalizedProviderTelemetry]:
    """Transform OpenRouter usage records (simulated or raw) into Qorvexis normalized models."""
    
    records = raw.get("data", [])
    if not records:
        return []

    telemetry_list = []
    
    for r in records:
        prompt = r.get("n_context_tokens_total", 0)
        completion = r.get("n_generated_tokens_total", 0)
        model = r.get("snapshot_id", "default")
        requests = r.get("n_requests", 0)
        latency = r.get("estimated_latency_ms", 800.0)
        
        # Generic mixed cost estimate
        cost_per_token = 0.000001
        estimated_cost = (prompt + completion) * cost_per_token
        
        telemetry_list.append(NormalizedProviderTelemetry(
            provider="openrouter",
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            latency=float(latency),
            estimated_cost=estimated_cost,
            request_count=requests,
        ))

    return telemetry_list
