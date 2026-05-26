"""Cost awareness tracker — heuristic token and cost estimation."""

import logging
import threading

logger = logging.getLogger("qorvexis.cost")

# Rough cost-per-1K-tokens estimates (USD). These are heuristic only.
_COST_PER_1K_TOKENS: dict[str, float] = {
    "gemini": 0.00025,
    "groq": 0.00027,
}

_TOKEN_MULTIPLIER = 1.3  # rough words-to-tokens ratio


class CostTracker:
    """Heuristic operational cost estimation.

    Estimates token count from prompt/response word count and applies
    rough per-provider cost rates. No billing integration — purely
    informational.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_prompt_tokens = 0
        self._total_response_tokens = 0
        self._total_estimated_cost = 0.0
        self._request_count = 0
        self._cost_by_provider: dict[str, float] = {}
        self._tokens_by_provider: dict[str, int] = {}

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        word_count = len(text.split())
        return max(1, round(word_count * _TOKEN_MULTIPLIER))

    def record_request(self, provider: str, prompt: str, response: str) -> float:
        prompt_tokens = self._estimate_tokens(prompt)
        response_tokens = self._estimate_tokens(response)
        total_tokens = prompt_tokens + response_tokens
        cost_rate = _COST_PER_1K_TOKENS.get(provider, 0.00025)
        estimated_cost = (total_tokens / 1000) * cost_rate

        with self._lock:
            self._total_prompt_tokens += prompt_tokens
            self._total_response_tokens += response_tokens
            self._total_estimated_cost += estimated_cost
            self._request_count += 1
            self._cost_by_provider[provider] = (
                self._cost_by_provider.get(provider, 0.0) + estimated_cost
            )
            self._tokens_by_provider[provider] = (
                self._tokens_by_provider.get(provider, 0) + total_tokens
            )

        logger.info(
            "cost.record provider=%s prompt_tokens=%s response_tokens=%s estimated_cost=%.6f",
            provider,
            prompt_tokens,
            response_tokens,
            estimated_cost,
        )
        return estimated_cost

    def get_cost_summary(self) -> dict:
        with self._lock:
            avg_cost = (
                self._total_estimated_cost / self._request_count
                if self._request_count
                else 0
            )
            providers = []
            for provider in sorted(self._cost_by_provider.keys()):
                tokens = self._tokens_by_provider.get(provider, 0)
                cost = self._cost_by_provider.get(provider, 0.0)
                rate = _COST_PER_1K_TOKENS.get(provider, 0.00025)
                providers.append(
                    {
                        "provider": provider,
                        "total_tokens": tokens,
                        "estimated_cost": round(cost, 6),
                        "cost_per_1k_tokens": rate,
                    }
                )

            return {
                "total_estimated_cost": round(self._total_estimated_cost, 6),
                "total_prompt_tokens": self._total_prompt_tokens,
                "total_response_tokens": self._total_response_tokens,
                "total_requests": self._request_count,
                "average_cost_per_request": round(avg_cost, 6),
                "providers": providers,
            }


cost_tracker = CostTracker()
