"""Contract tests for the disabled-by-default Nebius provider."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from ml_analyser.agent.models import (
    AnalysisContext,
    EvidenceKind,
    EvidenceRecord,
    FileCategory,
    GraphNodeType,
    Hypothesis,
    HypothesisKind,
    InventoryFile,
    MetricDirection,
    MetricExpectation,
    Objective,
    ProjectNode,
    ProjectStateGraph,
    RepositoryInventory,
    SuccessContract,
)
from ml_analyser.agent.providers import (
    NebiusTokenFactoryProvider,
    ProviderConfigurationError,
    ProviderResponseError,
    build_model_provider,
)
from ml_analyser.core.config import Settings


def _context() -> AnalysisContext:
    inventory = RepositoryInventory(
        project_root="/workspace/demo",
        files=[
            InventoryFile(
                path="train.py",
                size_bytes=20,
                category=FileCategory.SOURCE,
                language="Python",
                sha256="a" * 64,
            )
        ],
        total_files=1,
        total_bytes=20,
        category_counts={"source": 1},
    )
    evidence = EvidenceRecord(
        id="evidence_observed",
        kind=EvidenceKind.INVENTORY,
        claim="Observed one Python source file.",
        source="/workspace/demo",
    )
    return AnalysisContext(
        project_id="demo",
        success_contract=SuccessContract(
            objective=Objective(metric="f1", direction=MetricDirection.MAXIMIZE)
        ),
        inventory=inventory,
        state_graph=ProjectStateGraph(
            project_id="demo",
            nodes=[ProjectNode(id="demo", type=GraphNodeType.PROJECT, label="demo")],
            edges=[],
        ),
        evidence=[evidence],
    )


def _hypothesis(*, evidence_id: str = "evidence_observed") -> Hypothesis:
    return Hypothesis(
        id="hypothesis_nebius",
        kind=HypothesisKind.DIAGNOSTIC,
        statement="Class imbalance may be limiting F1.",
        rationale="The repository contains a training entry point.",
        proposed_intervention="Measure class distribution before changing training.",
        expected_outcome=MetricExpectation(
            metric="f1", direction=MetricDirection.MAXIMIZE, minimum_delta=0.0
        ),
        rejection_criteria="Reject if the observed labels are balanced.",
        evidence_ids=[evidence_id],
        priority=70,
    )


def test_nebius_provider_sends_structured_request_and_parses_hypotheses() -> None:
    observed_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request
        observed_request = request
        content = json.dumps({"hypotheses": [_hypothesis().model_dump(mode="json")]})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": content}}]},
        )

    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient(transport=transport)
    provider = NebiusTokenFactoryProvider(
        api_key="test-only-key",
        model="nvidia/test-nemotron",
        client=async_client,
    )
    try:
        result = asyncio.run(provider.propose_hypotheses(_context()))
    finally:
        asyncio.run(async_client.aclose())

    assert result == [_hypothesis()]
    assert observed_request is not None
    assert observed_request.url == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert observed_request.headers["Authorization"] == "Bearer test-only-key"
    request_body = json.loads(observed_request.content)
    assert request_body["model"] == "nvidia/test-nemotron"
    assert request_body["temperature"] == 0
    assert request_body["response_format"]["type"] == "json_schema"
    assert "train.py" in request_body["messages"][1]["content"]


def test_nebius_provider_rejects_ungrounded_hypothesis() -> None:
    content = json.dumps(
        {"hypotheses": [_hypothesis(evidence_id="evidence_invented").model_dump(mode="json")]}
    )
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )
    )
    async_client = httpx.AsyncClient(transport=transport)
    provider = NebiusTokenFactoryProvider(
        api_key="test-only-key",
        model="nvidia/test-nemotron",
        client=async_client,
    )
    try:
        with pytest.raises(ProviderResponseError, match="unobserved evidence"):
            asyncio.run(provider.propose_hypotheses(_context()))
    finally:
        asyncio.run(async_client.aclose())


def test_nebius_provider_rejects_malformed_response() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"choices": []}))
    async_client = httpx.AsyncClient(transport=transport)
    provider = NebiusTokenFactoryProvider(
        api_key="test-only-key",
        model="nvidia/test-nemotron",
        client=async_client,
    )
    try:
        with pytest.raises(ProviderResponseError, match="hypothesis contract"):
            asyncio.run(provider.propose_hypotheses(_context()))
    finally:
        asyncio.run(async_client.aclose())


def test_provider_factory_fails_closed_without_credentials(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        model_provider="nebius",
        state_database=tmp_path / "runs.db",
        nebius_api_key=None,
        nebius_model=None,
    )

    with pytest.raises(ProviderConfigurationError, match="NEBIUS_API_KEY"):
        build_model_provider(settings)


def test_nebius_constructor_requires_https() -> None:
    with pytest.raises(ProviderConfigurationError, match="HTTPS"):
        NebiusTokenFactoryProvider(
            api_key="test-only-key",
            model="nvidia/test-nemotron",
            base_url="http://example.invalid/v1",
        )
