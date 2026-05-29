"""Phase 10A — OpenAI Usage Adapter.

Responsible for retrieving historical usage data directly from OpenAI's API.
Abstracted away so if OpenAI changes their endpoint, only this file changes.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
import httpx

logger = logging.getLogger("qorvexis.connectors.openai.usage")


class OpenAIUsageProvider:
    """Adapter for OpenAI's /v1/usage endpoint."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1"
        self.client = httpx.Client(timeout=15.0)

    def fetch_daily_usage(self, target_date: datetime) -> dict:
        """Fetch total token usage for a specific day from OpenAI."""
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{self.base_url}/usage?date={date_str}"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            res = self.client.get(url, headers=headers)
            res.raise_for_status()
            data = res.json()

            # OpenAI returns a list of data points under 'data'
            # We aggregate them for the entire day.
            total_requests = 0
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            models: dict[str, int] = {}

            for item in data.get("data", []):
                if "n_requests" in item:
                    total_requests += item["n_requests"]
                
                # Context tokens (prompt)
                p_toks = item.get("n_context_tokens_total", 0)
                prompt_tokens += p_toks
                
                # Generated tokens (completion)
                c_toks = item.get("n_generated_tokens_total", 0)
                completion_tokens += c_toks
                
                t_toks = p_toks + c_toks
                total_tokens += t_toks

                model_name = item.get("snapshot_id", "unknown")
                models[model_name] = models.get(model_name, 0) + t_toks

            return {
                "requests": total_requests,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "model_distribution": models,
            }

        except Exception as exc:
            logger.warning("openai.usage_fetch_failed date=%s error=%s", date_str, exc)
            raise
        finally:
            self.client.close()
