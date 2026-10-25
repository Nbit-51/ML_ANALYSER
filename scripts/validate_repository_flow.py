"""Import trusted GitHub source and execute its declared ML evaluation end to end.

This is an owner-operated validation tool. The legacy ML adapter is not a hostile-code
sandbox. Review the source before explicitly approving its execution.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from ml_analyser.adapters.registry import default_registry
from ml_analyser.agent.analytics import persist_workbench_result, read_report
from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.models import SuccessContract
from ml_analyser.agent.providers import build_model_provider
from ml_analyser.core.config import get_settings
from ml_analyser.core.workspace import resolve_project_path
from ml_analyser.execution.workspace import IsolatedWorkspaceManager
from ml_analyser.persistence.sqlite import SQLiteRunStore
from ml_analyser.tools.capabilities import detect_capabilities
from ml_analyser.tools.import_repository import github_archive, save_files
from ml_analyser.tools.repository import RepositoryInventoryTool


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="https://github.com/Nbit-51/ML_ANALYSER")
    parser.add_argument("--evaluation", default="workspaces/ml-training-demo")
    parser.add_argument("--output", type=Path, default=Path("artifacts/repository-validation"))
    parser.add_argument(
        "--live", action="store_true", help="Use configured Nebius inference credits"
    )
    parser.add_argument("--approve-trusted-code", action="store_true")
    args = parser.parse_args()
    if not args.approve_trusted_code:
        parser.error("Review the repository, then explicitly pass --approve-trusted-code.")
    directory = args.output / str(uuid4())
    imported, count, skipped = save_files(directory / "imports", github_archive(args.repo))
    project_path = imported + "/" + args.evaluation
    root = resolve_project_path(directory / "imports", project_path)
    payload = json.loads((root / "prepare_request.json").read_text(encoding="utf-8"))
    contract = SuccessContract.model_validate(payload["success_contract"])
    settings = get_settings().model_copy(
        update={"model_provider": "nebius" if args.live else "mock"}
    )
    provider = build_model_provider(settings)
    store = SQLiteRunStore(directory / "runs.db")
    approvals = ApprovalService(store)
    inspector = RepositoryInventoryTool()
    registration = default_registry().get("ml_training")
    pipeline = registration.pipeline(
        provider=provider,
        inspector=inspector,
        approvals=approvals,
        evaluator=DecisionEvaluator(),
        workspaces=IsolatedWorkspaceManager(directory / "executions"),
        store=store,
    )
    prepared = await pipeline.prepare(
        project_id="public-repository-validation",
        project_path=project_path,
        project_root=root,
        success_contract=contract,
    )
    approvals.decide(
        prepared.approval.id,
        approved=True,
        reason="Explicit owner-operated CLI validation of trusted source.",
    )
    result = pipeline.execute(
        plan=prepared.plan, approval_id=prepared.approval.id, project_root=root
    )
    summary, _ = detect_capabilities(prepared.inventory)
    report = persist_workbench_result(
        store,
        "ml_training",
        result,
        prepared.plan,
        registration.normalize(result, prepared.plan),
        summary,
    )
    assert read_report(store, report.run_id) == report
    assert not report.original_project_modified
    (directory / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    objective = report.decision.objective
    print("Source:", args.repo)
    print("Evaluation:", args.evaluation)
    print("Imported files / exclusions:", count, skipped)
    print("Provider:", provider.name)
    print("Decision:", report.decision.status.value)
    if objective:
        print(
            "Measured",
            objective.metric,
            ":",
            objective.baseline_value,
            "->",
            objective.candidate_value,
        )
    print("Guardrails:", [(item.metric, item.passed) for item in report.decision.constraints])
    print("Original source unchanged; persisted report reopened successfully.")
    print("Report:", directory / "report.json")
    return 0 if report.decision.status == "accepted" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as error:
        print(f"Repository validation failed: {type(error).__name__}: {error}")
        raise SystemExit(1) from None
