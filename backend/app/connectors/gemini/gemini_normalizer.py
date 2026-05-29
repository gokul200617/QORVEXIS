"""Provider-specific normalizer for Gemini telemetry."""

from app.connectors.normalization.normalized_models import NormalizedProviderTelemetry


def transform_gemini_usage(raw: dict) -> list[NormalizedProviderTelemetry]:
    """Transform Gemini usage records (simulated or raw) into Qorvexis normalized models."""
    
    records = raw.get("data", [])
    if not records:
        return []

    telemetry_list = []
    
    for r in records:
        prompt = r.get("n_context_tokens_total", 0)
        completion = r.get("n_generated_tokens_total", 0)
        model = r.get("snapshot_id", "default")
        requests = r.get("n_requests", 0)
        latency = r.get("estimated_latency_ms", 1000.0)
        
        # Gemini 1.5 Flash rough cost: $0.00035 / 1K prompt, $0.00105 / 1K completion
        cost_per_prompt = 0.00000035
        cost_per_completion = 0.00000105
        estimated_cost = (prompt * cost_per_prompt) + (completion * cost_per_completion)
        
        telemetry_list.append(NormalizedProviderTelemetry(
            provider="gemini",
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            latency=float(latency),
            estimated_cost=estimated_cost,
            request_count=requests,
        ))

    return telemetry_list
