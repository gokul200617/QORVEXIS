from app.gateway.providers.openai_gateway_provider import OpenAIGatewayProvider

class GroqGatewayProvider(OpenAIGatewayProvider):
    """Adapter for Groq models (OpenAI compatible)."""
    
    def __init__(self):
        super().__init__(base_url="https://api.groq.com/openai/v1")
