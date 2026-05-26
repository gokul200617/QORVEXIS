from groq import Groq

from app.providers.base import InferenceProvider, ProviderError, ProviderUnavailableError
from app.settings import settings


class GroqProvider(InferenceProvider):
    name = "groq"
    model = "llama-3.3-70b-versatile"

    def __init__(self) -> None:
        if not settings.groq_api_key:
            raise ProviderUnavailableError("GROQ_API_KEY is not configured.")

        self._client = Groq(
            api_key=settings.groq_api_key,
            timeout=settings.provider_timeout_seconds,
        )

    def generate_response(self, prompt: str) -> str:
        try:
            completion = self._client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the inference layer inside Qorvexis, an "
                            "infrastructure orchestration platform. Return a "
                            "clear, concise technical response."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
            )
        except Exception as exc:
            raise ProviderError(f"Groq inference failed: {exc}") from exc

        message = completion.choices[0].message
        if not message.content:
            raise ProviderError("Groq returned an empty response.")

        return message.content
