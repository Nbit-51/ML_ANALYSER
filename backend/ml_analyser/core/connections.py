"""Configuration readiness without exposing credentials or making billable requests."""

from typing import Literal

from pydantic import Field

from ml_analyser.agent.models import StrictModel
from ml_analyser.core.config import Settings


class ConnectionCheck(StrictModel):
    status: Literal["configured", "incomplete", "not_configured", "disabled"]
    message: str
    missing_settings: list[str] = Field(default_factory=list)
    verification: Literal["not_tested"] = "not_tested"


class ConnectionSummary(StrictModel):
    app_url: str
    callback_url: str
    deployment_mode: str
    settings_location: str
    local_demo_available: bool
    github: ConnectionCheck
    nebius: ConnectionCheck
    live_lab_enabled: bool
    live_lab_daily_limit: int


def connection_summary(settings: Settings) -> ConnectionSummary:
    github_missing = [
        name
        for name, present in (
            ("ML_ANALYSER_GITHUB_CLIENT_ID", bool(settings.github_client_id.strip())),
            (
                "ML_ANALYSER_GITHUB_CLIENT_SECRET",
                bool(settings.github_client_secret.get_secret_value().strip()),
            ),
            ("ML_ANALYSER_GITHUB_ALLOWED_USERS", bool(settings.github_allowed_logins)),
        )
        if not present
    ]
    nebius_missing = [
        name
        for name, present in (
            ("ML_ANALYSER_MODEL_PROVIDER=nebius", settings.model_provider == "nebius"),
            (
                "NEBIUS_API_KEY",
                bool(
                    settings.nebius_api_key and settings.nebius_api_key.get_secret_value().strip()
                ),
            ),
            ("NEBIUS_MODEL", bool(settings.nebius_model and settings.nebius_model.strip())),
        )
        if not present
    ]
    github_status: Literal["configured", "incomplete", "not_configured", "disabled"] = (
        "configured"
        if not github_missing
        else "incomplete"
        if settings.auth_enabled
        else "not_configured"
    )
    nebius_status: Literal["configured", "incomplete", "not_configured", "disabled"] = (
        "configured"
        if not nebius_missing
        else "disabled"
        if nebius_missing == ["ML_ANALYSER_MODEL_PROVIDER=nebius"]
        else "incomplete"
        if len(nebius_missing) < 3
        else "not_configured"
    )
    return ConnectionSummary(
        app_url=settings.app_url,
        callback_url=settings.app_url + "/api/v1/auth/callback",
        deployment_mode=settings.deployment_mode,
        settings_location="host environment settings"
        if settings.deployment_mode == "judge"
        else "local .env",
        local_demo_available=settings.deployment_mode == "local" and not settings.auth_enabled,
        github=ConnectionCheck(
            status=github_status,
            message=(
                "Configuration is present. A browser sign-in must still verify it."
                if not github_missing
                else "Complete the listed settings to enable GitHub sign-in."
            ),
            missing_settings=github_missing,
        ),
        nebius=ConnectionCheck(
            status=nebius_status,
            message=(
                "Configuration is present. A live inference request must still verify it."
                if not nebius_missing
                else "Complete the listed settings to enable live reasoning."
            ),
            missing_settings=nebius_missing,
        ),
        live_lab_enabled=not nebius_missing and settings.lab_daily_limit > 0,
        live_lab_daily_limit=settings.lab_daily_limit,
    )
