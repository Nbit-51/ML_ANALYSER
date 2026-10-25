"""Actual cache measurements, independent replay and the public execution boundary."""

import asyncio
import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from ml_analyser.api.routes import lab
from ml_analyser.core.config import Settings, get_settings
from ml_analyser.lab.engine import LabReasoner, Proposal, digest, measure, replay
from ml_analyser.lab.store import LabStore
from ml_analyser.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "state.db"))
    monkeypatch.setenv("ML_ANALYSER_LAB_DAILY_LIMIT", "10")
    monkeypatch.setenv("ML_ANALYSER_LAB_COOLDOWN_SECONDS", "0")
    get_settings.cache_clear()
    return TestClient(app)


def prepared(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/lab/prepare", json={"mode": "offline"})
    assert response.status_code == 201, response.text
    return dict(response.json())


def execute(client: TestClient, data: dict[str, Any]) -> httpx.Response:
    return client.post(
        "/api/v1/lab/execute",
        json={
            "plan": data["plan"],
            "approval_id": data["approval"]["id"],
            "approved": True,
        },
    )


def test_actual_campaign_and_independent_replay(client: TestClient) -> None:
    data = prepared(client)
    assert "seed" not in data["plan"]
    assert data["approval"]["status"] == "pending"
    assert "def quote(" in data["source"]
    report = execute(client, data).json()
    assert report["model_calls"] == 0
    assert report["model_tokens"] == 0
    assert report["plan"]["provider"] == "offline-scripted-policy"
    assert report["winner_attempt"] == 3
    assert [a["decision"]["status"] for a in report["attempts"]] == [
        "rejected",
        "rejected",
        "accepted",
    ]
    control = report["negative_control"]
    assert control["discovery"]["incorrect_quotes"] == 0
    assert control["candidate"]["incorrect_quotes"] > 0
    assert control["candidate"]["reference_lookups"] < control["baseline"]["reference_lookups"]
    assert len(control["counterexamples"]) == 3
    winner = report["attempts"][-1]
    assert winner["baseline"]["reference_lookups"] == 120
    assert winner["candidate"] == {"reference_lookups": 30, "incorrect_quotes": 0}
    assert len(winner["paired_rounds"]) == 3
    assert winner["decision"]["benchmark_reliability"]["status"] == "reliable"
    assert replay(report) == []
    assert execute(client, data).status_code == 409
    _, evidence = lab.stores()
    assert len(evidence.list_for_run(data["plan"]["run_id"])) == 5


def test_capsule_detects_tampering_even_with_recomputed_digest(client: TestClient) -> None:
    original = execute(client, prepared(client)).json()
    for change in ("metric", "seed", "winner", "control", "scope", "proposal", "empty"):
        report = copy.deepcopy(original)
        if change == "metric":
            report["attempts"][0]["candidate"]["incorrect_quotes"] = 0
        elif change == "seed":
            report["challenge_seed_reveal"] = "different"
        elif change == "winner":
            report["winner_attempt"] = 1
        elif change == "control":
            report["negative_control"]["discovery"]["incorrect_quotes"] = 7
        elif change == "scope":
            report["plan"]["max_attempts"] = 99
        elif change == "proposal":
            report["plan"]["first_proposal"]["rationale"] = "altered"
        else:
            report["attempts"] = []
        report.pop("capsule_sha256")
        report["capsule_sha256"] = digest(report)
        assert replay(report), change
    original["stop_reason"] = "edited"
    assert "Capsule digest differs." in replay(original)


def test_capsule_survives_browser_number_serialization(client: TestClient) -> None:
    report = execute(client, prepared(client)).json()

    def browser_numbers(value: Any) -> Any:
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {key: browser_numbers(item) for key, item in value.items()}
        if isinstance(value, list):
            return [browser_numbers(item) for item in value]
        return value

    assert replay(browser_numbers(report)) == []


def test_captured_live_evidence_replays_without_credentials() -> None:
    example = Path(__file__).resolve().parents[2] / "frontend/examples/cache-capsule-live.json"
    report = json.loads(example.read_text(encoding="utf-8"))
    assert report["model_calls"] == 1
    assert report["plan"]["provider"].startswith("nebius-token-factory:nvidia/")
    assert replay(report) == []


def test_replay_checks_protocol_sequence(client: TestClient) -> None:
    report = execute(client, prepared(client)).json()
    report["schema_version"] = 2
    report["attempts"].append(copy.deepcopy(report["attempts"][-1]))
    report.pop("capsule_sha256")
    report["capsule_sha256"] = digest(report)
    errors = replay(report)
    assert "Unsupported capsule schema." in errors
    assert "Campaign continued after accepting a candidate." in errors
    assert "Campaign repeated an already tested configuration." in errors


def test_approval_tamper_browser_ownership_and_source_change(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = prepared(client)
    changed = copy.deepcopy(data)
    changed["plan"]["max_attempts"] = 999
    assert execute(client, changed).status_code == 409
    changed = copy.deepcopy(data)
    changed["approval"]["id"] = "wrong"
    assert execute(client, changed).status_code == 409
    other = TestClient(app)
    assert execute(other, data).status_code == 409
    other.cookies.set("ml_lab", "x" * 43)
    assert execute(other, data).status_code == 409
    monkeypatch.setattr(lab, "source_text", lambda: "different source")
    assert execute(client, data).status_code == 409


def test_no_code_input_no_implicit_approval(client: TestClient) -> None:
    assert (
        client.post("/api/v1/lab/prepare", json={"mode": "offline", "code": "print(1)"}).status_code
        == 422
    )
    data = prepared(client)
    response = client.post(
        "/api/v1/lab/execute",
        json={"plan": data["plan"], "approval_id": data["approval"]["id"], "approved": False},
    )
    assert response.status_code == 422
    for fields in (["sku", "sku"], ["__class__"], []):
        with pytest.raises(ValidationError):
            Proposal(cache_fields=fields, rationale="invalid")


def test_judge_profile_blocks_repository_execution_but_serves_lab(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ML_ANALYSER_DEPLOYMENT_MODE", "judge")
    get_settings.cache_clear()
    assert "Reduce repeated work." in client.get("/lab").text
    assert client.get("/app", follow_redirects=False).headers["location"] == "/lab"
    for endpoint in (
        "/runs/prepare",
        "/runs/execute",
        "/runs/start",
        "/repositories/folder",
        "/runs/preview",
    ):
        assert client.post("/api/v1" + endpoint, json={}).status_code == 403
    assert execute(client, prepared(client)).status_code == 200


def test_live_disabled_and_prepare_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client.get("/api/v1/lab/status").json()["live_available"] is False
    assert client.post("/api/v1/lab/prepare", json={"mode": "live"}).status_code == 503
    monkeypatch.setenv("ML_ANALYSER_LAB_COOLDOWN_SECONDS", "60")
    get_settings.cache_clear()
    prepared(client)
    response = client.post("/api/v1/lab/prepare", json={})
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_atomic_quota_and_expiry(tmp_path: Path) -> None:
    store = LabStore(tmp_path / "lab.db")

    def reserve(index: int) -> bool:
        try:
            store.reserve(str(index), str(index), live=True, limit=2, cooldown=0)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=5) as pool:
        assert sum(pool.map(reserve, range(10))) == 2
    store.reserve("offline", "owner", live=False, limit=0, cooldown=0)
    with pytest.raises(ValueError, match="not found"):
        store.load("offline", "owner")
    store.save_plan("offline", {"test": True})
    assert store.load("offline", "owner") == {"test": True}
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute("UPDATE lab_runs SET created = 0 WHERE id = 'offline'")
    with pytest.raises(ValueError, match="expired"):
        store.load("offline", "owner")


def test_provider_contract_and_actual_counterexample_feedback() -> None:
    previous = [measure(Proposal(cache_fields=["sku"], rationale="initial"), "seed", 1)]

    async def run() -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert payload["max_tokens"] == 2200
            sent = json.loads(payload["messages"][1]["content"])
            assert sent["previous_attempts"][0]["counterexamples"]
            assert "seed" not in sent
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "cache_fields": ["sku", "currency", "tenant"],
                                        "rationale": "Account for tenant and currency.",
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"total_tokens": 123},
                },
            )

        settings = Settings(
            model_provider="nebius", NEBIUS_API_KEY="test-key", NEBIUS_MODEL="nvidia/test"
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            provider = LabReasoner(settings, transport)
            result = await provider.propose(previous)
            assert result.cache_fields == ["tenant", "sku", "currency"]
            assert provider.calls == 1 and provider.tokens == 123
        for response in (httpx.Response(503), httpx.Response(200, json={"choices": []})):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _, current=response: current)
            ) as transport:
                with pytest.raises(ValueError, match="no fallback"):
                    await LabReasoner(settings, transport).propose([])
        with pytest.raises(ValueError, match="Configure"):
            await LabReasoner(
                settings.model_copy(update={"nebius_api_key": SecretStr("")})
            ).propose([])

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["repeat", "error", "safe", "prepare_error", "provider_change"])
def test_model_stop_conditions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    async def propose(self: LabReasoner, previous: list[Any]) -> Proposal:
        if mode == "prepare_error" or (mode == "error" and previous):
            raise ValueError("Provider unavailable")
        fields = ["tenant", "sku", "currency"] if mode == "safe" else ["sku"]
        return Proposal(cache_fields=fields, rationale="Test provider contract")

    monkeypatch.setattr(LabReasoner, "propose", propose)
    if mode == "prepare_error":
        assert client.post("/api/v1/lab/prepare", json={}).status_code == 502
        return
    data = prepared(client)
    if mode == "provider_change":
        monkeypatch.setattr(LabReasoner, "name", property(lambda self: "changed"))
        assert execute(client, data).status_code == 409
        return
    report = execute(client, data).json()
    assert len(report["attempts"]) == 1
    assert report["winner_attempt"] == (1 if mode == "safe" else None)
    assert replay(report) == []
