"""Environment-backed application settings."""

from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
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
    nebius_response_format: Literal["json_schema", "json_object"] = "json_schema"
    app_url: str = "http://127.0.0.1:8000"
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    github_allowed_users: str = ""
    auth_database: Path = Path("artifacts/auth.db")

    @field_validator("app_url")
    @classmethod
    def validate_app_url(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
            or (url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"})
        ):
            raise ValueError("App URL must be an HTTPS origin, or HTTP on localhost.")
        return value.rstrip("/")

    @property
    def auth_enabled(self) -> bool:
        return bool(self.github_client_id or self.github_client_secret.get_secret_value())

    @property
    def auth_ready(self) -> bool:
        return bool(
            self.github_client_id
            and self.github_client_secret.get_secret_value()
            and self.github_allowed_users.strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()


request_settings: ContextVar[Settings | None] = ContextVar("request_settings", default=None)


def get_request_settings() -> Settings:
    return request_settings.get() or get_settings()
