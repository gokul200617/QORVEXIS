"""Provider-specific normalizer for OpenAI telemetry."""

from app.connectors.normalization.normalization_engine import normalization_engine
from app.connectors.openai.openai_cost_engine import openai_cost_engine


def transform_openai_usage(raw: dict) -> dict:
    """Transform OpenAI usage records into Qorvexis normalized fields."""
    
    records = raw.get("data", [])
    if not records:
        return {}

    total_requests = 0
    total_prompt = 0
    total_completion = 0
    estimated_cost = 0.0

    for r in records:
        total_requests += r.get("n_requests", 0)
        prompt = r.get("n_context_tokens_total", 0)
        completion = r.get("n_generated_tokens_total", 0)
        model = r.get("snapshot_id", "default")
        
        total_prompt += prompt
        total_completion += completion
        estimated_cost += openai_cost_engine.estimate_cost(model, prompt, completion)

    # Simplified mock latency (OpenAI usage API does not expose latency natively)
    avg_latency = 800.0 if total_requests > 0 else 0.0

    return {
        "requests_per_minute": total_requests,
        "total_prompt_tokens": total_prompt,
        "total_response_tokens": total_completion,
        "estimated_cost_usd": estimated_cost,
        "average_latency_ms": avg_latency,
        "health_score": 100.0,
        "reliability_score": 100.0,
        "efficiency_score": 85.0,  # basic heuristic
        "waste_score": 5.0,        # basic heuristic
    }


# Register this transform with the generic engine so it automatically
# maps when the base engine sees the `openai` type.
normalization_engine.register_transform("openai", transform_openai_usage)
