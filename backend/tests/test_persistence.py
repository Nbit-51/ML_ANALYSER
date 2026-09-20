"""Tests for append-only evidence and experiment lineage persistence."""

from pathlib import Path

import pytest

from ml_analyser.agent.models import EvidenceKind, EvidenceRecord, ExperimentSpec
from ml_analyser.persistence.sqlite import (
    DuplicateRecordError,
    SQLiteRunStore,
    UnknownParentExperimentError,
)


def _experiment(identifier: str, parent: str | None = None) -> ExperimentSpec:
    return ExperimentSpec(
        id=identifier,
        hypothesis_id=f"hypothesis-{identifier}",
        title=f"Experiment {identifier}",
        parent_experiment_id=parent,
        change_summary=["No project change in test fixture."],
        procedure=["Measure fixture."],
        measurements=["f1"],
    )


def test_evidence_is_append_only_and_ordered(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "state" / "runs.db")
    first = EvidenceRecord(
        id="evidence-1",
        kind=EvidenceKind.INVENTORY,
        claim="Observed repository inventory.",
        source="fixture",
    )
    second = EvidenceRecord(
        id="evidence-2",
        kind=EvidenceKind.MEASUREMENT,
        claim="Observed f1=0.75.",
        source="fixture",
    )

    store.append("run-1", first)
    store.append("run-1", second)

    assert store.list_for_run("run-1") == [first, second]
    with pytest.raises(DuplicateRecordError):
        store.append("run-1", first)


def test_experiment_dag_requires_parent_to_exist(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.db")
    root = _experiment("baseline")
    child = _experiment("candidate", parent="baseline")

    store.add_experiment("run-1", root)
    store.add_experiment("run-1", child)

    assert store.list_experiments("run-1") == [root, child]

    with pytest.raises(UnknownParentExperimentError):
        store.add_experiment("run-1", _experiment("orphan", parent="missing"))


def test_experiment_ids_are_immutable_within_a_run(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.db")
    experiment = _experiment("baseline")
    store.add_experiment("run-1", experiment)

    with pytest.raises(DuplicateRecordError):
        store.add_experiment("run-1", experiment)
