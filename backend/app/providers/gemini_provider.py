import google.generativeai as genai

from app.providers.base import InferenceProvider, ProviderError, ProviderUnavailableError
from app.settings import settings


class GeminiProvider(InferenceProvider):
    name = "gemini"
    model = "gemini-2.5-flash"

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY is not configured.")

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(self.model)

    def generate_response(self, prompt: str) -> str:
        try:
            response = self._model.generate_content(
                prompt,
                request_options={"timeout": settings.provider_timeout_seconds},
            )
        except Exception as exc:
            raise ProviderError(f"Gemini inference failed: {exc}") from exc

        text = getattr(response, "text", None)
        if not text:
            raise ProviderError("Gemini returned an empty response.")

        return text
