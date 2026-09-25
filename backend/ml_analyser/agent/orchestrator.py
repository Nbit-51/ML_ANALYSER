"""Read-only preview orchestrator for the first vertical slice."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from uuid import uuid4

from ml_analyser.adapters.registry import default_registry
from ml_analyser.agent.compiler import DryRunExperimentCompiler
from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import (
    AnalysisContext,
    EvidenceKind,
    EvidenceRecord,
    PreviewRunResult,
    RunState,
    SuccessContract,
)
from ml_analyser.agent.ports import ExperimentCompiler, ModelProvider, RepositoryInspector
from ml_analyser.agent.providers import ProviderResponseError
from ml_analyser.agent.state import RunLifecycle
from ml_analyser.agent.state_graph import InventoryStateGraphBuilder
from ml_analyser.tools.capabilities import detect_capabilities
from ml_analyser.tools.repository_context import RepositoryContextTool


class PreviewOrchestrator:
    """Run ingestion through experiment design without executing project code."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        inspector: RepositoryInspector,
        graph_builder: InventoryStateGraphBuilder | None = None,
        compiler: ExperimentCompiler | None = None,
    ) -> None:
        self._provider = provider
        self._inspector = inspector
        self._graph_builder = graph_builder or InventoryStateGraphBuilder()
        self._compiler = compiler or DryRunExperimentCompiler()

    async def preview(
        self,
        *,
        project_id: str,
        project_root: Path,
        success_contract: SuccessContract,
    ) -> PreviewRunResult:
        lifecycle = RunLifecycle()
        lifecycle.transition(RunState.INGESTING)
        inventory = self._inspector.inspect(str(project_root))
        state_graph = self._graph_builder.build(project_id, inventory)

        category_summary = (
            ", ".join(
                f"{category}={count}" for category, count in inventory.category_counts.items()
            )
            or "no files"
        )
        snapshot_parts = [
            f"{item.path}:{item.sha256 or item.hash_status}" for item in inventory.files
        ]
        inventory_evidence = EvidenceRecord(
            id=stable_id("evidence", project_id, "inventory", *snapshot_parts),
            kind=EvidenceKind.INVENTORY,
            claim=(
                f"Observed {inventory.total_files} files ({inventory.total_bytes} bytes): "
                f"{category_summary}."
            ),
            source=inventory.project_root,
            content_hash=stable_id("snapshot", project_id, *snapshot_parts),
            metadata={
                "total_files": inventory.total_files,
                "total_bytes": inventory.total_bytes,
                "skipped_paths": len(inventory.skipped_paths),
            },
        )
        evidence = [
            inventory_evidence,
            *RepositoryContextTool().collect(project_root, inventory, success_contract),
        ]
        summary, capability_evidence = detect_capabilities(inventory)
        summary.adapters = default_registry().describe(project_root)
        # Capability facts stay inspectable; bounded excerpts alone enter model context.

        lifecycle.transition(RunState.DIAGNOSING)
        context = AnalysisContext(
            project_id=project_id,
            success_contract=success_contract,
            inventory=inventory,
            state_graph=state_graph,
            evidence=evidence,
        )

        lifecycle.transition(RunState.HYPOTHESIZING)
        hypotheses = await self._provider.propose_hypotheses(context)
        known_ids = {item.id for item in evidence}
        if any(set(item.evidence_ids) - known_ids for item in hypotheses):
            raise ProviderResponseError("provider referenced nonexistent evidence IDs")

        lifecycle.transition(RunState.DESIGNING)
        experiments = [self._compiler.compile(hypothesis, context) for hypothesis in hypotheses]

        lifecycle.transition(RunState.SELECTING)
        lifecycle.transition(RunState.REPORTING)
        lifecycle.transition(RunState.COMPLETED)

        warning_counts = Counter(
            item.hash_status for item in inventory.files if item.hash_status != "complete"
        )
        warnings = [
            "Preview mode is read-only: no project code, command, or experiment was executed.",
            "Experiment commands remain unresolved until a domain adapter validates them.",
        ]
        warnings.extend(
            f"{count} file(s) have hash status '{status}'."
            for status, count in sorted(warning_counts.items())
        )
        if inventory.skipped_paths:
            warnings.append(
                f"Inventory skipped {len(inventory.skipped_paths)} path(s); inspect skipped_paths."
            )

        return PreviewRunResult(
            run_id=str(uuid4()),
            project_id=project_id,
            provider=self._provider.name,
            final_state=lifecycle.current,
            state_history=lifecycle.history,
            inventory=inventory,
            state_graph=state_graph,
            evidence=[*evidence, *capability_evidence],
            hypotheses=hypotheses,
            experiments=experiments,
            warnings=warnings,
            repository_summary=summary,
            success_contract=success_contract,
        )
