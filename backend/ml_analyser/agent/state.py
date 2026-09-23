"""Run-state transition enforcement."""

from __future__ import annotations

from collections.abc import Callable

from ml_analyser.agent.models import RunState

TERMINAL_STATES = frozenset({RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED})

ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.INGESTING, RunState.CANCELLED, RunState.FAILED}),
    RunState.INGESTING: frozenset({RunState.DIAGNOSING, RunState.CANCELLED, RunState.FAILED}),
    RunState.DIAGNOSING: frozenset(
        {RunState.HYPOTHESIZING, RunState.REPORTING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.HYPOTHESIZING: frozenset(
        {RunState.DESIGNING, RunState.REPORTING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.DESIGNING: frozenset(
        {RunState.SELECTING, RunState.REPORTING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.SELECTING: frozenset(
        {
            RunState.AWAITING_APPROVAL,
            RunState.REPORTING,
            RunState.CANCELLED,
            RunState.FAILED,
        }
    ),
    RunState.AWAITING_APPROVAL: frozenset(
        {RunState.EXECUTING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.EXECUTING: frozenset({RunState.MEASURING, RunState.CANCELLED, RunState.FAILED}),
    RunState.MEASURING: frozenset({RunState.DECIDING, RunState.CANCELLED, RunState.FAILED}),
    RunState.DECIDING: frozenset(
        {RunState.REVISING, RunState.REPORTING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.REVISING: frozenset(
        {RunState.HYPOTHESIZING, RunState.REPORTING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.REPORTING: frozenset({RunState.COMPLETED, RunState.FAILED}),
    RunState.COMPLETED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


class InvalidStateTransition(ValueError):
    """Raised when a run attempts an illegal lifecycle transition."""


class RunLifecycle:
    """Small state machine that records every legal transition."""

    def __init__(self, on_transition: Callable[[RunState], None] | None = None) -> None:
        self._current = RunState.CREATED
        self._history = [RunState.CREATED]
        self._on_transition = on_transition

    @property
    def current(self) -> RunState:
        return self._current

    @property
    def history(self) -> list[RunState]:
        return list(self._history)

    def transition(self, next_state: RunState) -> None:
        if next_state not in ALLOWED_TRANSITIONS[self._current]:
            raise InvalidStateTransition(
                f"cannot transition from {self._current.value} to {next_state.value}"
            )
        self._current = next_state
        self._history.append(next_state)
        if self._on_transition is not None:
            self._on_transition(next_state)
