"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings for the API process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ML_ANALYSER_",
        extra="ignore",
    )

    app_name: str = "ML Analyser API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_v1_prefix: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()

