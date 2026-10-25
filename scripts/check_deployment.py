"""Verify hosted configuration and a real lab run without handling server credentials."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from ml_analyser.evaluation.predictions import (
    PredictionReport,
    PredictionRequest,
    compare_predictions,
)
from ml_analyser.lab.engine import replay


def check(
    base_url: str,
    *,
    mode: str | None,
    require_connections: bool,
    output: Path,
    predictions: bool = False,
) -> int:
    origin = urlsplit(base_url)
    if (
        origin.scheme not in {"https", "http"}
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.query
        or origin.fragment
        or origin.path not in {"", "/"}
        or (origin.scheme == "http" and origin.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise ValueError("Use an HTTPS origin, or localhost HTTP, without credentials or a path.")
    checks: dict[str, object] = {}
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=240, follow_redirects=False) as client:
        health = client.get("/api/v1/health")
        health.raise_for_status()
        assert health.json()["status"] == "ok", "Service health failed."
        checks["service_health"] = "passed"
        connections = client.get("/api/v1/connections")
        connections.raise_for_status()
        state = connections.json()
        checks["github_configuration"] = state["github"]["status"]
        checks["nebius_configuration"] = state["nebius"]["status"]
        checks["live_lab_enabled"] = state["live_lab_enabled"]
        checks["oauth_callback"] = state["callback_url"]
        checks["missing_github_settings"] = state["github"]["missing_settings"]
        checks["missing_nebius_settings"] = state["nebius"]["missing_settings"]
        assert state["callback_url"] == base_url.rstrip("/") + "/api/v1/auth/callback", (
            "OAuth callback origin differs from the deployed URL."
        )
        if state["deployment_mode"] == "judge":
            assert not state["local_demo_available"], "Hosted local-demo bypass must stay disabled."
            app = client.get("/app")
            assert app.status_code == 303 and app.headers["location"] == "/login"
            assert client.get("/api/v1/runs/history").status_code in {401, 403}
            checks["anonymous_workspace_boundary"] = "passed"
        if predictions:
            assert client.get("/evaluate").status_code == 200
            prediction_checks = {}
            for name, task, expected in (
                ("classification-improvement", "classification", "accepted"),
                ("hidden-regression", "classification", "rejected"),
                ("regression-improvement", "regression", "accepted"),
            ):
                example = client.get(f"/static/examples/predictions-{name}.csv")
                example.raise_for_status()
                request = PredictionRequest.model_validate(
                    {
                        "task": task,
                        "csv_text": example.text,
                        "primary_metric": "f1_macro" if task == "classification" else "rmse",
                        "minimum_improvement": 0.01 if task == "classification" else 0.1,
                        "maximum_slice_regression": 0.02 if task == "classification" else 0.1,
                    }
                )
                response = client.post("/api/v1/evaluation/compare", json=request.model_dump())
                response.raise_for_status()
                report = PredictionReport.model_validate(response.json())
                assert report.decision == expected, name
                assert compare_predictions(request) == report, f"Prediction replay differs: {name}"
                output.mkdir(parents=True, exist_ok=True)
                (output / f"prediction-{name}-{report.report_sha256[:12]}.json").write_text(
                    report.model_dump_json(indent=2) + "\n",
                    encoding="utf-8",
                )
                prediction_checks[name] = report.decision
            checks["prediction_comparison_and_independent_replay"] = prediction_checks
        if mode:
            if mode == "live" and not state["live_lab_enabled"]:
                raise ValueError(
                    "Live lab is not enabled. Configure Nebius and a positive daily quota."
                )
            prepared = client.post("/api/v1/lab/prepare", json={"mode": mode})
            prepared.raise_for_status()
            data = prepared.json()
            payload = {
                "plan": data["plan"],
                "approval_id": data["approval"]["id"],
                "approved": True,
            }
            tampered = copy.deepcopy(payload)
            tampered["plan"]["max_attempts"] += 1
            assert client.post("/api/v1/lab/execute", json=tampered).status_code == 409
            result = client.post("/api/v1/lab/execute", json=payload)
            result.raise_for_status()
            report = result.json()
            assert replay(report) == [], "Hosted report does not replay on this checkout."
            assert report["negative_control"]["decision"]["status"] == "rejected"
            assert client.post("/api/v1/lab/execute", json=payload).status_code == 409
            assert (report["model_calls"] > 0) == (mode == "live")
            output.mkdir(parents=True, exist_ok=True)
            run_id = str(UUID(report["plan"]["run_id"]))
            report_path = output / f"{mode}-{run_id}.json"
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            checks["lab_mode"] = mode
            checks["measured_attempts"] = len(report["attempts"])
            checks["winner_attempt"] = report["winner_attempt"]
            checks["report_replay"] = "passed"
            checks["approval_tamper_and_replay_denial"] = "passed"
            checks["report_path"] = str(report_path)
        checks["github_browser_sign_in"] = (
            "manual verification required; configuration is not a live OAuth test"
        )
        ready = state["github"]["status"] == state["nebius"]["status"] == "configured"
        if require_connections:
            ready = ready and state["live_lab_enabled"]
        checks["requested_checks_passed"] = ready if require_connections else True
        print(json.dumps(checks, indent=2))
        return 0 if checks["requested_checks_passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Deployed HTTPS origin, or localhost HTTP")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--exercise-lab", action="store_true", help="Run an actual offline campaign"
    )
    actions.add_argument(
        "--live-lab",
        action="store_true",
        help="Opt in to a live campaign using hosted Nebius credits",
    )
    parser.add_argument("--require-connections", action="store_true")
    parser.add_argument(
        "--predictions",
        action="store_true",
        help="Compare and replay all three prediction examples without inference",
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/connection-checks"))
    args = parser.parse_args()
    try:
        return check(
            args.url,
            mode="live" if args.live_lab else "offline" if args.exercise_lab else None,
            require_connections=args.require_connections,
            output=args.output,
            predictions=args.predictions,
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AssertionError) as error:
        print(f"Deployment check failed: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
