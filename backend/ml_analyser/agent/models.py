"""Typed domain models for evidence-driven optimization runs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base model that rejects unknown input fields."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RunState(StrEnum):
    CREATED = "created"
    INGESTING = "ingesting"
    DIAGNOSING = "diagnosing"
    HYPOTHESIZING = "hypothesizing"
    DESIGNING = "designing"
    SELECTING = "selecting"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    MEASURING = "measuring"
    DECIDING = "deciding"
    REVISING = "revising"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MetricDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class ConstraintOperator(StrEnum):
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    GTE = "gte"
    GT = "gt"


class Objective(StrictModel):
    metric: str = Field(min_length=1, max_length=120)
    direction: MetricDirection
    target: float | None = None
    minimum_improvement: float = Field(default=0.0, ge=0.0)


class MetricConstraint(StrictModel):
    metric: str = Field(min_length=1, max_length=120)
    operator: ConstraintOperator
    threshold: float
    tolerance: float = Field(default=0.0, ge=0.0)


class ComputeBudget(StrictModel):
    max_cost_usd: float | None = Field(default=None, ge=0.0)
    max_wall_clock_seconds: int | None = Field(default=None, ge=1)
    max_cpu_seconds: int | None = Field(default=None, ge=1)
    max_gpu_seconds: int | None = Field(default=None, ge=1)
    max_model_tokens: int | None = Field(default=None, ge=1)
    max_experiments: int | None = Field(default=None, ge=1)


class SuccessContract(StrictModel):
    objective: Objective
    constraints: list[MetricConstraint] = Field(default_factory=list)
    budget: ComputeBudget = Field(default_factory=ComputeBudget)

    @field_validator("constraints")
    @classmethod
    def constraints_must_have_unique_metrics(
        cls, constraints: list[MetricConstraint]
    ) -> list[MetricConstraint]:
        names = [constraint.metric.casefold() for constraint in constraints]
        if len(names) != len(set(names)):
            raise ValueError("constraint metrics must be unique")
        return constraints


class FileCategory(StrEnum):
    SOURCE = "source"
    TEST = "test"
    CONFIGURATION = "configuration"
    DATA = "data"
    MODEL_ARTIFACT = "model_artifact"
    METRICS = "metrics"
    DOCUMENTATION = "documentation"
    NOTEBOOK = "notebook"
    OTHER = "other"


class InventoryFile(StrictModel):
    path: str
    size_bytes: int = Field(ge=0)
    category: FileCategory
    language: str | None = None
    sha256: str | None = None
    hash_status: str = "complete"


class RepositoryInventory(StrictModel):
    project_root: str
    files: list[InventoryFile]
    skipped_paths: list[str] = Field(default_factory=list)
    total_files: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    category_counts: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def totals_must_match_files(self) -> RepositoryInventory:
        if self.total_files != len(self.files):
            raise ValueError("total_files must match files")
        if self.total_bytes != sum(item.size_bytes for item in self.files):
            raise ValueError("total_bytes must match file sizes")
        return self


class GraphNodeType(StrEnum):
    PROJECT = "project"
    CATEGORY = "category"
    FILE = "file"
    CAPABILITY = "capability"
    LANGUAGE = "language"
    EXPERIMENT = "experiment"
    MEASUREMENT = "measurement"
    ARTIFACT = "artifact"


class GraphEdgeType(StrEnum):
    CONTAINS = "contains"
    USES = "uses"
    CONFIGURES = "configures"
    TESTS = "tests"
    MEASURES = "measures"
    PRODUCES = "produces"
    DEPENDS_ON = "depends_on"
    GENERATED_BY = "generated_by"


MetadataValue = str | int | float | bool | None


class ProjectNode(StrictModel):
    id: str
    type: GraphNodeType
    label: str
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class ProjectEdge(StrictModel):
    source_id: str
    target_id: str
    type: GraphEdgeType
    provenance: str = "detected"
    confidence: float = Field(default=1, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ProjectStateGraph(StrictModel):
    project_id: str
    nodes: list[ProjectNode]
    edges: list[ProjectEdge]


class EvidenceKind(StrEnum):
    INVENTORY = "inventory"
    SOURCE = "source"
    CONFIGURATION = "configuration"
    TOOL_OUTPUT = "tool_output"
    MEASUREMENT = "measurement"


class EvidenceRecord(StrictModel):
    id: str
    kind: EvidenceKind
    claim: str
    source: str
    content_hash: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class HypothesisKind(StrEnum):
    BASELINE = "baseline"
    DIAGNOSTIC = "diagnostic"
    OPTIMIZATION = "optimization"
    RELIABILITY = "reliability"


class MetricExpectation(StrictModel):
    metric: str
    direction: MetricDirection
    minimum_delta: float = Field(default=0.0, ge=0.0)


class Hypothesis(StrictModel):
    id: str
    kind: HypothesisKind
    statement: str
    rationale: str
    proposed_intervention: str
    expected_outcome: MetricExpectation
    rejection_criteria: str
    evidence_ids: list[str] = Field(min_length=1)
    priority: int = Field(ge=1, le=100)


class ExperimentStatus(StrEnum):
    COMPILED = "compiled"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    MEASURED = "measured"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


class DecisionStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSUMED = "consumed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExperimentSpec(StrictModel):
    id: str
    hypothesis_id: str
    title: str
    parent_experiment_id: str | None = None
    change_summary: list[str]
    procedure: list[str]
    command: list[str] | None = None
    measurements: list[str]
    estimated_budget: ComputeBudget = Field(default_factory=ComputeBudget)
    requires_approval: bool = True
    status: ExperimentStatus = ExperimentStatus.COMPILED


class MetricDefinition(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    label: str | None = None
    unit: str | None = Field(default=None, max_length=40)
    direction: MetricDirection | None = None
    minimum: float | None = None
    maximum: float | None = None


class SampleSummary(StrictModel):
    count: int = Field(ge=1)
    mean: float
    median: float
    minimum: float
    maximum: float
    p50: float
    p90: float
    p95: float
    p99: float
    standard_deviation: float = Field(ge=0)
    coefficient_of_variation: float | None = None


class ArtifactRecord(StrictModel):
    id: str
    path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    content_base64: str


class Measurement(StrictModel):
    metric: str = Field(min_length=1, max_length=120)
    value: float = Field(strict=True)
    unit: str | None = Field(default=None, max_length=40)
    evidence_ids: list[str] = Field(min_length=1)
    label: str | None = None
    direction: MetricDirection | None = None
    raw_samples: list[float] = Field(default_factory=list, max_length=10000)
    reliability_samples: list[float] = Field(default_factory=list, max_length=10000)
    summary: SampleSummary | None = None
    warmup_count: int = Field(default=0, ge=0)
    failed_sample_count: int = Field(default=0, ge=0)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    environment_fingerprint: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class BenchmarkReliability(StrictModel):
    status: str = "not_assessed"
    reasons: list[str] = Field(default_factory=list)
    minimum_samples: int = 3
    maximum_cv: float = 0.30
    environment_compatible: bool | None = None
    statistical_significance_tested: bool = False


class Capability(StrictModel):
    id: str
    name: str
    kind: str
    provenance: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    paths: list[str]


class AdapterReadiness(StrictModel):
    adapter: str
    status: str
    reason: str
    profiles: list[str] = Field(default_factory=list)
    required_configuration: str | None = None
    supported_measurements: list[str] = Field(default_factory=list)


class RepositorySummary(StrictModel):
    composition_basis: str = "bytes of inventoried source files"
    language_bytes: dict[str, int] = Field(default_factory=dict)
    capabilities: list[Capability] = Field(default_factory=list)
    adapters: list[AdapterReadiness] = Field(default_factory=list)


class ResourceUsage(StrictModel):
    cost_usd: float = Field(default=0.0, ge=0.0)
    wall_clock_seconds: float = Field(default=0.0, ge=0.0)
    cpu_seconds: float = Field(default=0.0, ge=0.0)
    gpu_seconds: float = Field(default=0.0, ge=0.0)
    model_tokens: int = Field(default=0, ge=0)
    experiments: int = Field(default=1, ge=0)


class ObjectiveEvaluation(StrictModel):
    metric: str
    baseline_value: float
    candidate_value: float
    improvement: float
    target_passed: bool
    minimum_improvement_passed: bool
    passed: bool


class ConstraintEvaluation(StrictModel):
    metric: str
    operator: ConstraintOperator
    threshold: float
    observed_value: float | None = None
    passed: bool
    reason: str


class BudgetEvaluation(StrictModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)
    usage: ResourceUsage


class DecisionRecord(StrictModel):
    experiment_id: str
    status: DecisionStatus
    objective: ObjectiveEvaluation | None = None
    constraints: list[ConstraintEvaluation] = Field(default_factory=list)
    budget: BudgetEvaluation
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    benchmark_reliability: BenchmarkReliability = Field(default_factory=BenchmarkReliability)


class ApprovalRecord(StrictModel):
    id: str
    run_id: str
    experiment_id: str
    scope_fingerprint: str
    summary: str
    risk_level: RiskLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    reason: str | None = None


class AnalysisContext(StrictModel):
    project_id: str
    success_contract: SuccessContract
    inventory: RepositoryInventory
    state_graph: ProjectStateGraph
    evidence: list[EvidenceRecord]


class PreviewRunResult(StrictModel):
    run_id: str
    project_id: str
    provider: str
    final_state: RunState
    state_history: list[RunState]
    inventory: RepositoryInventory
    state_graph: ProjectStateGraph
    evidence: list[EvidenceRecord]
    hypotheses: list[Hypothesis]
    experiments: list[ExperimentSpec]
    warnings: list[str]
    repository_summary: RepositorySummary = Field(default_factory=RepositorySummary)
    success_contract: SuccessContract | None = None
