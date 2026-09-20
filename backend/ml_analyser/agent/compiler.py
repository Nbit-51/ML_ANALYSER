"""Compile typed hypotheses into non-executed experiment specifications."""

from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import (
    AnalysisContext,
    ComputeBudget,
    ExperimentSpec,
    Hypothesis,
)


class DryRunExperimentCompiler:
    """Produce reproducible intent while leaving commands to domain adapters."""

    def compile(self, hypothesis: Hypothesis, context: AnalysisContext) -> ExperimentSpec:
        measurements = [context.success_contract.objective.metric]
        measurements.extend(
            constraint.metric for constraint in context.success_contract.constraints
        )
        unique_measurements = list(dict.fromkeys(measurements))

        return ExperimentSpec(
            id=stable_id("experiment", context.project_id, hypothesis.id),
            hypothesis_id=hypothesis.id,
            title=f"Test: {hypothesis.statement}",
            change_summary=[hypothesis.proposed_intervention],
            procedure=[
                "Resolve the adapter-specific baseline and measurement commands.",
                "Create an isolated candidate workspace from the accepted project state.",
                "Capture baseline measurements with environment and artifact provenance.",
                "Apply only the compiled intervention after policy approval.",
                "Measure the candidate with the same compatible procedure.",
                "Evaluate the objective and every guardrail; keep or revert the candidate.",
            ],
            command=None,
            measurements=unique_measurements,
            estimated_budget=ComputeBudget(
                max_wall_clock_seconds=60,
                max_experiments=1,
            ),
            requires_approval=True,
        )
