import json
import httpx
from typing import AsyncGenerator
from app.gateway.providers.gateway_base_provider import BaseGatewayProvider

class OpenAIGatewayProvider(BaseGatewayProvider):
    """Adapter for OpenAI models."""
    
    def __init__(self, base_url: str = "https://api.openai.com/v1"):
        self.base_url = base_url
        self.timeout = 60

    def generate(self, api_key: str, model: str, messages: list[dict[str, str]], **kwargs) -> tuple[str, int, int]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        
        # Merge any specific headers passed by child classes (e.g. OpenRouter)
        extra_headers = kwargs.get("extra_headers", {})
        headers.update(extra_headers)

        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            
        res.raise_for_status()
        data = res.json()

        content = data["choices"][0]["message"].get("content", "")
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        
        return content, prompt_tokens, completion_tokens

    async def generate_stream(self, api_key: str, model: str, messages: list[dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
            "stream": True,
        }
        
        extra_headers = kwargs.get("extra_headers", {})
        headers.update(extra_headers)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=body) as response:
                response.raise_for_status()
                async for chunk in response.aiter_lines():
                    if chunk.startswith("data: ") and chunk != "data: [DONE]":
                        try:
                            data = json.loads(chunk[6:])
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue

    def supports_streaming(self) -> bool:
        return True

    def health_check(self, api_key: str) -> bool:
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            with httpx.Client(timeout=10) as client:
                res = client.get(f"{self.base_url}/models", headers=headers)
                return res.status_code == 200
        except Exception:
            return False
