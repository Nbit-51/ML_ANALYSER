"""Deterministic objective, guardrail, and budget evaluation."""

from __future__ import annotations

from collections.abc import Iterable

from ml_analyser.agent.measurements import assess_reliability
from ml_analyser.agent.models import (
    BudgetEvaluation,
    ComputeBudget,
    ConstraintEvaluation,
    ConstraintOperator,
    DecisionRecord,
    DecisionStatus,
    Measurement,
    MetricConstraint,
    MetricDirection,
    ObjectiveEvaluation,
    ResourceUsage,
    SuccessContract,
)


class DecisionEvaluator:
    """Apply deterministic acceptance rules without model discretion."""

    def evaluate(
        self,
        *,
        experiment_id: str,
        contract: SuccessContract,
        baseline: Iterable[Measurement],
        candidate: Iterable[Measurement],
        usage: ResourceUsage,
    ) -> DecisionRecord:
        baseline_by_metric = self._index_measurements(baseline)
        candidate_by_metric = self._index_measurements(candidate)
        budget = self._evaluate_budget(contract.budget, usage)

        required_metrics = {
            contract.objective.metric,
            *(constraint.metric for constraint in contract.constraints),
        }
        missing = sorted(required_metrics - candidate_by_metric.keys())
        if contract.objective.metric not in baseline_by_metric:
            missing.append(f"baseline:{contract.objective.metric}")
        if missing:
            return DecisionRecord(
                experiment_id=experiment_id,
                status=DecisionStatus.INCONCLUSIVE,
                budget=budget,
                reason=f"Missing required measurement(s): {', '.join(sorted(missing))}.",
                evidence_ids=self._evidence_ids(baseline_by_metric, candidate_by_metric),
            )

        baseline_objective = baseline_by_metric[contract.objective.metric]
        candidate_objective = candidate_by_metric[contract.objective.metric]
        reliability = assess_reliability(
            list(baseline_by_metric.values()), list(candidate_by_metric.values()), required_metrics
        )
        if reliability.reasons:
            return DecisionRecord(
                experiment_id=experiment_id,
                status=DecisionStatus.INCONCLUSIVE,
                budget=budget,
                reason="; ".join(reliability.reasons),
                benchmark_reliability=reliability,
                evidence_ids=self._evidence_ids(baseline_by_metric, candidate_by_metric),
            )
        if baseline_objective.unit != candidate_objective.unit:
            return DecisionRecord(
                experiment_id=experiment_id,
                status=DecisionStatus.INCONCLUSIVE,
                budget=budget,
                reason="Baseline and candidate objective units are incompatible.",
                evidence_ids=self._evidence_ids(baseline_by_metric, candidate_by_metric),
            )

        objective = self._evaluate_objective(
            contract=contract,
            baseline=baseline_objective,
            candidate=candidate_objective,
        )
        constraints = [
            self._evaluate_constraint(constraint, candidate_by_metric[constraint.metric])
            for constraint in contract.constraints
        ]
        passed = objective.passed and all(item.passed for item in constraints) and budget.passed
        failed_parts: list[str] = []
        if not objective.passed:
            failed_parts.append("objective")
        if not all(item.passed for item in constraints):
            failed_parts.append("guardrail")
        if not budget.passed:
            failed_parts.append("budget")

        return DecisionRecord(
            experiment_id=experiment_id,
            status=DecisionStatus.ACCEPTED if passed else DecisionStatus.REJECTED,
            objective=objective,
            constraints=constraints,
            budget=budget,
            reason=(
                "Objective, guardrails, and budget passed."
                if passed
                else f"Rejected because the {', '.join(failed_parts)} check failed."
            ),
            evidence_ids=self._evidence_ids(baseline_by_metric, candidate_by_metric),
            benchmark_reliability=reliability,
        )

    @staticmethod
    def _index_measurements(measurements: Iterable[Measurement]) -> dict[str, Measurement]:
        indexed: dict[str, Measurement] = {}
        for measurement in measurements:
            if measurement.metric in indexed:
                raise ValueError(f"duplicate measurement: {measurement.metric}")
            indexed[measurement.metric] = measurement
        return indexed

    @staticmethod
    def _evidence_ids(
        baseline: dict[str, Measurement], candidate: dict[str, Measurement]
    ) -> list[str]:
        return list(
            dict.fromkeys(
                evidence_id
                for measurement in [*baseline.values(), *candidate.values()]
                for evidence_id in measurement.evidence_ids
            )
        )

    @staticmethod
    def _evaluate_objective(
        *,
        contract: SuccessContract,
        baseline: Measurement,
        candidate: Measurement,
    ) -> ObjectiveEvaluation:
        objective = contract.objective
        if objective.direction is MetricDirection.MAXIMIZE:
            improvement = candidate.value - baseline.value
            target_passed = objective.target is None or candidate.value >= objective.target
        else:
            improvement = baseline.value - candidate.value
            target_passed = objective.target is None or candidate.value <= objective.target

        improvement_passed = improvement >= objective.minimum_improvement
        return ObjectiveEvaluation(
            metric=objective.metric,
            baseline_value=baseline.value,
            candidate_value=candidate.value,
            improvement=improvement,
            target_passed=target_passed,
            minimum_improvement_passed=improvement_passed,
            passed=target_passed and improvement_passed,
        )

    @staticmethod
    def _evaluate_constraint(
        constraint: MetricConstraint, measurement: Measurement
    ) -> ConstraintEvaluation:
        observed = measurement.value
        threshold = constraint.threshold
        tolerance = constraint.tolerance
        match constraint.operator:
            case ConstraintOperator.LT:
                passed = observed < threshold + tolerance
            case ConstraintOperator.LTE:
                passed = observed <= threshold + tolerance
            case ConstraintOperator.EQ:
                passed = abs(observed - threshold) <= tolerance
            case ConstraintOperator.GTE:
                passed = observed >= threshold - tolerance
            case ConstraintOperator.GT:
                passed = observed > threshold - tolerance

        return ConstraintEvaluation(
            metric=constraint.metric,
            operator=constraint.operator,
            threshold=threshold,
            observed_value=observed,
            passed=passed,
            reason=(
                f"Observed {observed} passes {constraint.operator.value} {threshold}."
                if passed
                else f"Observed {observed} fails {constraint.operator.value} {threshold}."
            ),
        )

    @staticmethod
    def _evaluate_budget(budget: ComputeBudget, usage: ResourceUsage) -> BudgetEvaluation:
        comparisons = (
            ("cost_usd", budget.max_cost_usd, usage.cost_usd),
            ("wall_clock_seconds", budget.max_wall_clock_seconds, usage.wall_clock_seconds),
            ("cpu_seconds", budget.max_cpu_seconds, usage.cpu_seconds),
            ("gpu_seconds", budget.max_gpu_seconds, usage.gpu_seconds),
            ("model_tokens", budget.max_model_tokens, usage.model_tokens),
            ("experiments", budget.max_experiments, usage.experiments),
        )
        violations = [
            f"{name}: used {actual}, limit {limit}"
            for name, limit, actual in comparisons
            if limit is not None and actual > limit
        ]
        return BudgetEvaluation(passed=not violations, violations=violations, usage=usage)
