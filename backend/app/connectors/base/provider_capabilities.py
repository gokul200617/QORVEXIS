"""Phase 10A — Provider Capabilities and Confidence Enums.

Distinguishes between provider limitations and connector failures.
Provides strict enums for data source and confidence tracking.
"""

from enum import Enum
from pydantic import BaseModel


class ProviderDataSource(str, Enum):
    """Origin of the telemetry data."""
    PROVIDER_API = "provider_api"  # Directly from provider's usage API
    GATEWAY      = "gateway"       # Observed via Qorvexis Gateway
    SIMULATION   = "simulation"    # Synthetic (only allowed if simulation_mode=True)
    MIXED        = "mixed"         # Combination of sources


class ProviderDataConfidence(str, Enum):
    """Trust level of the telemetry data."""
    REAL_PROVIDER_USAGE    = "real_provider_usage"    # Absolute truth (includes external traffic)
    REAL_GATEWAY_USAGE     = "real_gateway_usage"     # Truth, but only covers Gateway traffic
    PARTIAL_PROVIDER_USAGE = "partial_provider_usage" # Provider API used, but data might be delayed/partial
    SIMULATION             = "simulation"             # Not real data


class ProviderCapabilities(BaseModel):
    """Explicitly tracks what a provider supports.
    
    Prevents the system from assuming a feature exists when the provider
    fundamentally lacks the capability (e.g. Groq lacking usage endpoints).
    """
    supports_authentication: bool
    supports_usage_retrieval: bool
    supports_cost_retrieval: bool
    supports_model_discovery: bool
    supports_request_history: bool
    supports_spend_history: bool


# ── Initial Capability Mappings ───────────────────────────────────────────────

OPENAI_CAPABILITIES = ProviderCapabilities(
    supports_authentication=True,
    supports_usage_retrieval=True,
    supports_cost_retrieval=True,
    supports_model_discovery=True,
    supports_request_history=False, # Wait, does OpenAI support request-by-request history? No, just aggregate.
    supports_spend_history=False,
)

GROQ_CAPABILITIES = ProviderCapabilities(
    supports_authentication=True,
    supports_usage_retrieval=False,
    supports_cost_retrieval=False,
    supports_model_discovery=True,
    supports_request_history=False,
    supports_spend_history=False,
)

GEMINI_CAPABILITIES = ProviderCapabilities(
    supports_authentication=True,
    supports_usage_retrieval=False,
    supports_cost_retrieval=False,
    supports_model_discovery=True,
    supports_request_history=False,
    supports_spend_history=False,
)

OPENROUTER_CAPABILITIES = ProviderCapabilities(
    supports_authentication=True,
    supports_usage_retrieval=False,
    supports_cost_retrieval=False,
    supports_model_discovery=True,
    supports_request_history=False,
    supports_spend_history=False,
)

def get_capabilities_for_provider(provider_name: str) -> ProviderCapabilities:
    """Returns the capability matrix for a given provider."""
    normalized = provider_name.lower().strip()
    if normalized == "openai":
        return OPENAI_CAPABILITIES
    elif normalized == "groq":
        return GROQ_CAPABILITIES
    elif normalized == "gemini":
        return GEMINI_CAPABILITIES
    elif normalized == "openrouter":
        return OPENROUTER_CAPABILITIES
    
    # Default fallback
    return ProviderCapabilities(
        supports_authentication=True,
        supports_usage_retrieval=False,
        supports_cost_retrieval=False,
        supports_model_discovery=False,
        supports_request_history=False,
        supports_spend_history=False,
    )
