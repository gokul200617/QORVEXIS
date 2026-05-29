import logging
from app.gateway.providers.gateway_base_provider import BaseGatewayProvider

logger = logging.getLogger("qorvexis.gateway.registry")

class GatewayProviderRegistry:
    """Manages available provider adapters for the AI Gateway."""

    def __init__(self):
        self._providers: dict[str, BaseGatewayProvider] = {}

    def register(self, name: str, provider: BaseGatewayProvider) -> None:
        self._providers[name.lower()] = provider
        logger.info("gateway.registry.registered provider=%s", name)

    def get(self, name: str) -> BaseGatewayProvider | None:
        return self._providers.get(name.lower())

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

gateway_provider_registry = GatewayProviderRegistry()
