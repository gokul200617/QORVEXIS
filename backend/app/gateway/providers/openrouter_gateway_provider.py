from typing import AsyncGenerator
from app.gateway.providers.openai_gateway_provider import OpenAIGatewayProvider

class OpenRouterGatewayProvider(OpenAIGatewayProvider):
    """Adapter for OpenRouter models (OpenAI compatible, specific headers)."""
    
    def __init__(self):
        super().__init__(base_url="https://openrouter.ai/api/v1")

    def generate(self, api_key: str, model: str, messages: list[dict[str, str]], **kwargs) -> tuple[str, int, int]:
        kwargs["extra_headers"] = {
            "HTTP-Referer": "https://qorvexis.com",
            "X-Title": "Qorvexis Gateway"
        }
        return super().generate(api_key, model, messages, **kwargs)

    async def generate_stream(self, api_key: str, model: str, messages: list[dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        kwargs["extra_headers"] = {
            "HTTP-Referer": "https://qorvexis.com",
            "X-Title": "Qorvexis Gateway"
        }
        async for chunk in super().generate_stream(api_key, model, messages, **kwargs):
            yield chunk
