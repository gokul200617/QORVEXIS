"""Centralized pricing engine for all AI providers.

All cost calculations MUST flow through this module.
Provider-agnostic: works with OpenAI, Gemini, Groq heuristics.
"""

import logging

logger = logging.getLogger("qorvexis.token_intelligence.pricing")

# ── OpenAI model pricing (USD per 1,000 tokens) ───────────────────────────────
# Prompt / Completion costs as of 2025 baseline. Static reference.
_OPENAI_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
    "text-embedding-3-small": {"prompt": 0.00002, "completion": 0.0},
    "text-embedding-3-large": {"prompt": 0.00013, "completion": 0.0},
}

# ── Heuristic pricing for non-OpenAI providers ────────────────────────────────
# Word-count estimated tokens, rough provider rate. Informational only.
_PROVIDER_FALLBACK_RATE: dict[str, float] = {
    "gemini": 0.00025,
    "groq":   0.00027,
}

_DEFAULT_RATE = 0.00025


def _resolve_openai_pricing(model: str) -> dict[str, float] | None:
    """Fuzzy-match model string against known OpenAI pricing tiers."""
    model_lower = model.lower()
    for key, pricing in _OPENAI_PRICING.items():
        if key in model_lower:
            return pricing
    return None


def estimate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Compute estimated USD cost for a single request.

    Args:
        provider:          Provider name ('openai', 'gemini', 'groq').
        model:             Model identifier string.
        prompt_tokens:     Number of prompt tokens consumed.
        completion_tokens: Number of completion tokens generated.

    Returns:
        Estimated cost in USD (float).
    """
    provider_lower = provider.lower()

    # OpenAI — model-level pricing
    if "openai" in provider_lower:
        pricing = _resolve_openai_pricing(model)
        if pricing:
            cost = (
                (prompt_tokens / 1000.0) * pricing["prompt"]
                + (completion_tokens / 1000.0) * pricing["completion"]
            )
            return round(cost, 8)
        # Unknown OpenAI model: apply gpt-4o-mini rate as conservative default
        total = prompt_tokens + completion_tokens
        return round((total / 1000.0) * 0.0005, 8)

    # Groq / Gemini — flat heuristic rate on total tokens
    rate = _PROVIDER_FALLBACK_RATE.get(provider_lower, _DEFAULT_RATE)
    total_tokens = prompt_tokens + completion_tokens
    return round((total_tokens / 1000.0) * rate, 8)


def get_model_pricing_info(provider: str, model: str) -> dict:
    """Return pricing metadata for display in analytics."""
    provider_lower = provider.lower()
    if "openai" in provider_lower:
        pricing = _resolve_openai_pricing(model)
        if pricing:
            return {
                "prompt_per_1k_usd": pricing["prompt"],
                "completion_per_1k_usd": pricing["completion"],
                "tier": _classify_model_tier(model),
            }
    rate = _PROVIDER_FALLBACK_RATE.get(provider_lower, _DEFAULT_RATE)
    return {
        "prompt_per_1k_usd": rate,
        "completion_per_1k_usd": rate,
        "tier": "standard",
    }


def _classify_model_tier(model: str) -> str:
    """Classify model cost tier for efficiency analysis."""
    model_lower = model.lower()
    if "gpt-4o-mini" in model_lower or "embedding" in model_lower:
        return "economy"
    if "gpt-3.5" in model_lower:
        return "standard"
    if "gpt-4o" in model_lower:
        return "premium"
    if "gpt-4" in model_lower:
        return "ultra"
    return "standard"


def get_cheaper_alternative(model: str) -> str | None:
    """Return a cost-effective alternative model name, if applicable."""
    model_lower = model.lower()
    if "gpt-4o" in model_lower and "mini" not in model_lower:
        return "gpt-4o-mini"
    if "gpt-4-turbo" in model_lower or ("gpt-4" in model_lower and "turbo" in model_lower):
        return "gpt-4o-mini"
    if "gpt-4" in model_lower and "o" not in model_lower:
        return "gpt-4o"
    return None


def estimate_monthly_cost(avg_daily_cost_usd: float) -> float:
    """Project monthly cost from average daily spend."""
    return round(avg_daily_cost_usd * 30.0, 4)
