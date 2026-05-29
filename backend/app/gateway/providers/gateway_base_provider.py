from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator
from pydantic import BaseModel

class BaseGatewayProvider(ABC):
    """
    Abstract base class for all Qorvexis Gateway providers.
    Every provider integration must implement this interface to ensure uniform
    telemetry, routing, and cost estimation capabilities.
    """

    @abstractmethod
    def generate(self, api_key: str, model: str, messages: list[dict[str, str]], **kwargs) -> tuple[str, int, int]:
        """
        Execute a standard chat completion.
        Returns:
            Tuple containing: (content_string, prompt_tokens, completion_tokens)
        """
        pass

    @abstractmethod
    async def generate_stream(self, api_key: str, model: str, messages: list[dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        """
        Execute a streaming chat completion (SSE).
        Yields raw string chunks.
        """
        pass
        
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Returns True if the provider supports Server-Sent Events streaming."""
        return True

    @abstractmethod
    def health_check(self, api_key: str) -> bool:
        """Verify the provider is reachable and the credentials are valid."""
        pass
