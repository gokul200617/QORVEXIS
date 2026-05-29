import json
import httpx
from typing import AsyncGenerator
from app.gateway.providers.gateway_base_provider import BaseGatewayProvider

class GeminiGatewayProvider(BaseGatewayProvider):
    """Adapter for Google Gemini models."""
    
    def __init__(self):
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.timeout = 60

    def _convert_messages(self, messages: list[dict[str, str]]) -> list[dict]:
        contents = []
        for msg in messages:
            role = "user" if msg["role"] != "assistant" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        return contents

    def generate(self, api_key: str, model: str, messages: list[dict[str, str]], **kwargs) -> tuple[str, int, int]:
        url = f"{self.base_url}/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        body = {
            "contents": self._convert_messages(messages),
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 1024),
            }
        }

        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(url, headers=headers, json=body)
        res.raise_for_status()
        data = res.json()

        try:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            content = ""

        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        completion_tokens = usage.get("candidatesTokenCount", 0)
        
        return content, prompt_tokens, completion_tokens

    async def generate_stream(self, api_key: str, model: str, messages: list[dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/{model}:streamGenerateContent?alt=sse&key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        body = {
            "contents": self._convert_messages(messages),
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 1024),
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                response.raise_for_status()
                async for chunk in response.aiter_lines():
                    if chunk.startswith("data: "):
                        try:
                            data = json.loads(chunk[6:])
                            if "candidates" in data and len(data["candidates"]) > 0:
                                delta = data["candidates"][0]["content"]["parts"][0].get("text", "")
                                if delta:
                                    yield delta
                        except Exception:
                            continue

    def supports_streaming(self) -> bool:
        return True

    def health_check(self, api_key: str) -> bool:
        try:
            with httpx.Client(timeout=10) as client:
                res = client.get(f"{self.base_url}?key={api_key}")
                # Either 200 or 400 (if it wants a model specified) but not 401/403
                return res.status_code not in (401, 403)
        except Exception:
            return False
