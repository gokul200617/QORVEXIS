from app.gateway.gateway_provider_registry import gateway_provider_registry
from app.gateway.providers.openai_gateway_provider import OpenAIGatewayProvider
from app.gateway.providers.groq_gateway_provider import GroqGatewayProvider
from app.gateway.providers.gemini_gateway_provider import GeminiGatewayProvider
from app.gateway.providers.openrouter_gateway_provider import OpenRouterGatewayProvider

# Register standard gateway providers
gateway_provider_registry.register("openai", OpenAIGatewayProvider())
gateway_provider_registry.register("groq", GroqGatewayProvider())
gateway_provider_registry.register("gemini", GeminiGatewayProvider())
gateway_provider_registry.register("openrouter", OpenRouterGatewayProvider())
