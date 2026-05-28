import httpx

from app.providers.base import InferenceProvider, ProviderError, ProviderUnavailableError
from app.settings import settings
from app.connectors.registry.connector_registry import connector_registry
from app.connectors.base.connector_types import ConnectorType

class OpenAIProvider(InferenceProvider):
    name = "openai"
    model = "gpt-4o"
    
    def __init__(self) -> None:
        # Find the active OpenAI connector in the registry
        openai_connectors = [
            c for c in connector_registry.list_all()
            if c.connector_type == ConnectorType.AI_PROVIDER and "openai" in c.connector_id.lower()
        ]
        
        if not openai_connectors:
            raise ProviderUnavailableError("No active OpenAI connector found in registry.")
            
        self._connector = openai_connectors[0]
        # We can extract the API key from the connector's client. 
        # Since it's in memory, we can access it directly.
        self._api_key = getattr(self._connector._client, "api_key", None)
        if not self._api_key:
            raise ProviderUnavailableError("OpenAI connector missing API key.")
            
        self._client = httpx.Client(timeout=settings.provider_timeout_seconds)

    def generate_response(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        
        try:
            res = self._client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            res.raise_for_status()
            data = res.json()
            
            # OpenAI Usage tracking could go here natively, but for now we rely on the scheduled task
            # return the actual text
            return data["choices"][0]["message"]["content"]
            
        except httpx.TimeoutException as exc:
            raise ProviderError("OpenAI inference timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenAI inference failed: {exc}") from exc
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"OpenAI returned unexpected response schema: {exc}") from exc
