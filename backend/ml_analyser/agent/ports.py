"""Ports that isolate orchestration from providers, tools, and persistence."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel

from ml_analyser.agent.models import (
    AnalysisContext,
    ApprovalRecord,
    ApprovalStatus,
    EvidenceRecord,
    ExperimentSpec,
    Hypothesis,
    ProjectStateGraph,
    RepositoryInventory,
)


class ModelProvider(Protocol):
    """Structured reasoning provider used by the agent runtime."""

    @property
    def name(self) -> str: ...

    async def propose_hypotheses(self, context: AnalysisContext) -> list[Hypothesis]: ...


class RepositoryInspector(Protocol):
    """Read-only repository inventory port."""

    def inspect(self, project_root: str) -> RepositoryInventory: ...


class StateGraphBuilder(Protocol):
    """Builds a project state graph from observed repository state."""

    def build(self, project_id: str, inventory: RepositoryInventory) -> ProjectStateGraph: ...


class ExperimentCompiler(Protocol):
    """Compiles hypotheses into non-executed experiment specifications."""

    def compile(self, hypothesis: Hypothesis, context: AnalysisContext) -> ExperimentSpec: ...


class EvidenceLedger(Protocol):
    """Append-only evidence persistence port for a future implementation."""

    def append(self, run_id: str, evidence: EvidenceRecord) -> None: ...

    def list_for_run(self, run_id: str) -> Sequence[EvidenceRecord]: ...


class ExperimentDagStore(Protocol):
    """Persistent experiment-lineage port."""

    def add_experiment(self, run_id: str, experiment: ExperimentSpec) -> None: ...

    def list_experiments(self, run_id: str) -> Sequence[ExperimentSpec]: ...


class ApprovalStore(Protocol):
    """Persistent single-use execution approval port."""

    def create_approval(self, approval: ApprovalRecord) -> None: ...

    def get_approval(self, approval_id: str) -> ApprovalRecord | None: ...

    def decide_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        reason: str | None,
    ) -> ApprovalRecord: ...

    def consume_approval(self, approval_id: str, scope_fingerprint: str) -> ApprovalRecord: ...


class ToolRequest(BaseModel):
    """Base class for typed tool requests."""


class ToolResult(BaseModel):
    """Normalized tool result; raw output belongs in artifact storage."""

    succeeded: bool
    summary: str
    evidence: list[EvidenceRecord]


class Tool(Protocol):
    """Typed and auditable tool boundary."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    async def execute(self, request: ToolRequest) -> ToolResult: ...
