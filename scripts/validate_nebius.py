"""Read-only live provider smoke test; run only after Token Factory access is configured."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ml_analyser.agent.models import MetricDirection, Objective, SuccessContract
from ml_analyser.agent.orchestrator import PreviewOrchestrator
from ml_analyser.agent.providers import build_model_provider
from ml_analyser.core.config import get_settings
from ml_analyser.tools.repository import RepositoryInventoryTool


async def main() -> int:
    settings = get_settings()
    if settings.model_provider != "nebius":
        print("Set ML_ANALYSER_MODEL_PROVIDER=nebius before live validation.", file=sys.stderr)
        return 2
    project_root = Path("workspaces/ml-training-demo").resolve()
    provider = build_model_provider(settings)
    result = await PreviewOrchestrator(
        provider=provider,
        inspector=RepositoryInventoryTool(),
    ).preview(
        project_id="ml-training-demo",
        project_root=project_root,
        success_contract=SuccessContract(
            objective=Objective(metric="f1", direction=MetricDirection.MAXIMIZE)
        ),
    )
    print(f"Provider: {provider.name}")
    print(f"Read-only preview: {result.final_state.value}")
    print(f"Validated hypotheses: {len(result.hypotheses)}")
    for hypothesis in result.hypotheses:
        print(f"- {hypothesis.kind.value}: {hypothesis.statement}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as error:
        # Provider exceptions deliberately exclude credential values and response bodies.
        print(f"Live validation failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from None
