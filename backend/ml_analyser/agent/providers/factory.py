"""Provider selection from validated application settings."""

from ml_analyser.agent.ports import ModelProvider
from ml_analyser.agent.providers.mock import DeterministicMockProvider
from ml_analyser.agent.providers.nebius import (
    NebiusTokenFactoryProvider,
    ProviderConfigurationError,
)
from ml_analyser.core.config import Settings


def build_model_provider(settings: Settings) -> ModelProvider:
    """Build the configured provider, failing closed on incomplete credentials."""

    if settings.model_provider == "mock":
        return DeterministicMockProvider()

    api_key = (
        settings.nebius_api_key.get_secret_value().strip()
        if settings.nebius_api_key is not None
        else ""
    )
    model = (settings.nebius_model or "").strip()
    if not api_key or not model:
        raise ProviderConfigurationError(
            "Nebius provider requires both NEBIUS_API_KEY and NEBIUS_MODEL"
        )
    return NebiusTokenFactoryProvider(
        api_key=api_key,
        model=model,
        base_url=settings.nebius_base_url,
        timeout_seconds=settings.nebius_timeout_seconds,
        response_format=settings.nebius_response_format,
    )
