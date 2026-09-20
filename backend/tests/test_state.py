"""Tests for explicit run lifecycle transitions."""

import pytest

from ml_analyser.agent.models import RunState
from ml_analyser.agent.state import InvalidStateTransition, RunLifecycle


def test_preview_lifecycle_can_complete_without_execution() -> None:
    lifecycle = RunLifecycle()

    for state in (
        RunState.INGESTING,
        RunState.DIAGNOSING,
        RunState.HYPOTHESIZING,
        RunState.DESIGNING,
        RunState.SELECTING,
        RunState.REPORTING,
        RunState.COMPLETED,
    ):
        lifecycle.transition(state)

    assert lifecycle.current is RunState.COMPLETED
    assert RunState.EXECUTING not in lifecycle.history


def test_lifecycle_rejects_skipping_directly_to_execution() -> None:
    lifecycle = RunLifecycle()

    with pytest.raises(InvalidStateTransition, match="created to executing"):
        lifecycle.transition(RunState.EXECUTING)
