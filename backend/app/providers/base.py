from abc import ABC, abstractmethod


class ProviderError(Exception):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class InferenceProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        pass
