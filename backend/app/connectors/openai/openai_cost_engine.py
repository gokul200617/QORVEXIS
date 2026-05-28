"""Static cost engine for OpenAI tokens."""

import logging

logger = logging.getLogger("qorvexis.connectors.openai.cost")

# Approximate token pricing (USD per 1k tokens)
# Note: prices change frequently, this is a static baseline for phase 8B.
PRICING_TABLE = {
    "gpt-4o": {
        "prompt": 0.005,
        "completion": 0.015,
    },
    "gpt-4-turbo": {
        "prompt": 0.01,
        "completion": 0.03,
    },
    "gpt-4": {
        "prompt": 0.03,
        "completion": 0.06,
    },
    "gpt-3.5-turbo": {
        "prompt": 0.0005,
        "completion": 0.0015,
    },
    "text-embedding-3-small": {
        "prompt": 0.00002,
        "completion": 0.0,
    },
    "text-embedding-3-large": {
        "prompt": 0.00013,
        "completion": 0.0,
    },
    "default": {
        "prompt": 0.001,
        "completion": 0.002,
    }
}

class OpenAICostEngine:
    
    @staticmethod
    def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate the estimated USD cost for a given token usage."""
        
        # Resolve model key (e.g. 'gpt-4o-2024-05-13' -> 'gpt-4o')
        pricing = PRICING_TABLE.get("default")
        for key, p in PRICING_TABLE.items():
            if key in model:
                pricing = p
                break
                
        prompt_cost = (prompt_tokens / 1000.0) * pricing["prompt"]
        completion_cost = (completion_tokens / 1000.0) * pricing["completion"]
        
        return prompt_cost + completion_cost

openai_cost_engine = OpenAICostEngine()
