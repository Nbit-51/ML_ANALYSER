"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    workspace_root: Path = Path("workspaces")
    state_database: Path = Path("artifacts/ml_analyser.db")
    execution_root: Path = Path("artifacts/executions")
    model_provider: Literal["mock", "nebius"] = "mock"
    nebius_api_key: SecretStr | None = Field(default=None, validation_alias="NEBIUS_API_KEY")
    nebius_base_url: str = Field(
        default="https://api.tokenfactory.nebius.com/v1",
        validation_alias="NEBIUS_BASE_URL",
    )
    nebius_model: str | None = Field(default=None, validation_alias="NEBIUS_MODEL")
    nebius_timeout_seconds: float = Field(default=60.0, gt=0, le=300)


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()
