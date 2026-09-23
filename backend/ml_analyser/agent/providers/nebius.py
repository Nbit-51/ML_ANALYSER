"""Nebius Token Factory model-provider adapter."""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from pydantic import Field, ValidationError

from ml_analyser.agent.models import AnalysisContext, Hypothesis, StrictModel


class ProviderConfigurationError(ValueError):
    """Raised when an external provider is selected without usable configuration."""


class ProviderResponseError(RuntimeError):
    """Raised when a provider returns an unusable or invalid response."""


class HypothesisEnvelope(StrictModel):
    """Structured response required from a reasoning provider."""

    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=12)


class NebiusTokenFactoryProvider:
    """Generate typed hypotheses through Nebius's OpenAI-compatible API.

    The adapter is reasoning-only: it cannot execute commands or mutate repositories.
    A caller-supplied client is primarily useful for deterministic contract tests.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.tokenfactory.nebius.com/v1",
        timeout_seconds: float = 60.0,
        response_format: Literal["json_schema", "json_object"] = "json_schema",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderConfigurationError("NEBIUS_API_KEY is required for the Nebius provider")
        if not model.strip():
            raise ProviderConfigurationError("NEBIUS_MODEL is required for the Nebius provider")
        if not base_url.strip().lower().startswith("https://"):
            raise ProviderConfigurationError("NEBIUS_BASE_URL must be an HTTPS URL")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._response_format = response_format
        self._client = client

    @property
    def name(self) -> str:
        return f"nebius-token-factory:{self._model}"

    async def propose_hypotheses(self, context: AnalysisContext) -> list[Hypothesis]:
        payload = self._request_payload(context)
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                        timeout=self._timeout_seconds,
                    )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ProviderResponseError(f"Nebius request failed: {error}") from error

        envelope = self._parse_response(response)
        self._validate_grounding(envelope, context)
        return envelope.hypotheses

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request_payload(self, context: AnalysisContext) -> dict[str, Any]:
        schema = HypothesisEnvelope.model_json_schema()
        inventory = [
            {
                "path": item.path,
                "category": item.category,
                "language": item.language,
                "size_bytes": item.size_bytes,
            }
            for item in context.inventory.files[:200]
        ]
        observed_ids = [evidence.id for evidence in context.evidence]
        user_context = {
            "project_id": context.project_id,
            "success_contract": context.success_contract.model_dump(mode="json"),
            "inventory": inventory,
            "inventory_truncated": len(context.inventory.files) > len(inventory),
            "evidence": [evidence.model_dump(mode="json") for evidence in context.evidence],
            "allowed_evidence_ids": observed_ids,
        }
        format_spec: dict[str, Any] = (
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "ml_engineering_hypotheses",
                    "strict": True,
                    "schema": schema,
                },
            }
            if self._response_format == "json_schema"
            else {"type": "json_object"}
        )
        return {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the diagnostic reasoning component of an evidence-driven "
                        "engineering agent. Propose only falsifiable hypotheses grounded in the "
                        "provided evidence. Do not claim that commands ran or results were "
                        "observed. "
                        "If an evidence item declares the ml_training adapter, include an "
                        "optimization hypothesis about the declared configuration intervention. "
                        "Every evidence_ids value must come from allowed_evidence_ids. Return JSON "
                        "that exactly follows the supplied schema: "
                        f"{json.dumps(schema, separators=(',', ':'))}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(user_context, separators=(",", ":")),
                },
            ],
            "response_format": format_spec,
        }

    @staticmethod
    def _parse_response(response: httpx.Response) -> HypothesisEnvelope:
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError("message content is empty or not text")
            return HypothesisEnvelope.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise ProviderResponseError(
                "Nebius returned a response that does not match the hypothesis contract"
            ) from error

    @staticmethod
    def _validate_grounding(envelope: HypothesisEnvelope, context: AnalysisContext) -> None:
        allowed_evidence_ids = {evidence.id for evidence in context.evidence}
        objective_metric = context.success_contract.objective.metric.casefold()
        for hypothesis in envelope.hypotheses:
            if not set(hypothesis.evidence_ids).issubset(allowed_evidence_ids):
                raise ProviderResponseError("Nebius hypothesis referenced unobserved evidence")
            if hypothesis.expected_outcome.metric.casefold() != objective_metric:
                raise ProviderResponseError("Nebius hypothesis used a metric outside the objective")
