"""Gateway Cost Engine — estimates real-time cost for every proxied request.

Pricing tables are deterministic. No external calls.
All prices are per-1K-token in USD unless noted.
"""

from __future__ import annotations

# ── Pricing Table ─────────────────────────────────────────────────────────────
# Format: provider -> model -> (prompt_per_1k, completion_per_1k)
_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o":              (0.005,    0.015),
        "gpt-4o-mini":         (0.00015,  0.0006),
        "gpt-4-turbo":         (0.01,     0.03),
        "gpt-4":               (0.03,     0.06),
        "gpt-3.5-turbo":       (0.0005,   0.0015),
        "text-embedding-3-small": (0.00002, 0.0),
        "default":             (0.005,    0.015),
    },
    "groq": {
        "llama3-70b-8192":     (0.00059,  0.00079),
        "llama3-8b-8192":      (0.00005,  0.00008),
        "mixtral-8x7b-32768":  (0.00024,  0.00024),
        "gemma-7b-it":         (0.00007,  0.00007),
        "default":             (0.0007,   0.0009),
    },
    "gemini": {
        "gemini-1.5-pro":      (0.00125,  0.00375),
        "gemini-1.5-flash":    (0.000075, 0.0003),
        "gemini-1.0-pro":      (0.0005,   0.0015),
        "default":             (0.0005,   0.0015),
    },
    "openrouter": {
        "anthropic/claude-3-haiku":          (0.00025,  0.00125),
        "anthropic/claude-3-sonnet":         (0.003,    0.015),
        "meta-llama/llama-3-8b-instruct":    (0.00005,  0.00008),
        "mistralai/mistral-7b-instruct":     (0.00006,  0.00006),
        "default":                           (0.001,    0.003),
    },
}


class GatewayCostEngine:
    def estimate(self, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Returns estimated USD cost for this request."""
        provider_table = _PRICING.get(provider.lower(), _PRICING.get("openai"))
        # Try exact match, then partial match, then default
        pricing = provider_table.get(model)
        if pricing is None:
            for key in provider_table:
                if key != "default" and key in model:
                    pricing = provider_table[key]
                    break
        if pricing is None:
            pricing = provider_table.get("default", (0.005, 0.015))

        prompt_cost = (prompt_tokens / 1000) * pricing[0]
        completion_cost = (completion_tokens / 1000) * pricing[1]
        return prompt_cost + completion_cost


gateway_cost_engine = GatewayCostEngine()
