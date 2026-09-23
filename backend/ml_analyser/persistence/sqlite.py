"""SQLite-backed append-only evidence ledger and experiment DAG."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml_analyser.agent.models import (
    ApprovalRecord,
    ApprovalStatus,
    EvidenceRecord,
    ExperimentSpec,
)


class DuplicateRecordError(ValueError):
    """Raised when an append-only record identifier already exists."""


class UnknownParentExperimentError(ValueError):
    """Raised when a DAG node references a missing parent in the same run."""


class UnknownApprovalError(ValueError):
    """Raised when an approval identifier does not exist."""


class InvalidApprovalTransitionError(ValueError):
    """Raised when an approval cannot move to the requested status."""


class SQLiteRunStore:
    """Persist immutable evidence and experiment nodes in a local SQLite database."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def append(self, run_id: str, evidence: EvidenceRecord) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO evidence (run_id, evidence_id, payload)
                    VALUES (?, ?, ?)
                    """,
                    (run_id, evidence.id, evidence.model_dump_json()),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateRecordError(
                f"evidence '{evidence.id}' already exists for run '{run_id}'"
            ) from error

    def list_for_run(self, run_id: str) -> list[EvidenceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM evidence
                WHERE run_id = ?
                ORDER BY sequence ASC
                """,
                (run_id,),
            ).fetchall()
        return [EvidenceRecord.model_validate_json(row[0]) for row in rows]

    def add_experiment(self, run_id: str, experiment: ExperimentSpec) -> None:
        try:
            with self._connect() as connection:
                if experiment.parent_experiment_id is not None:
                    parent = connection.execute(
                        """
                        SELECT 1
                        FROM experiments
                        WHERE run_id = ? AND experiment_id = ?
                        """,
                        (run_id, experiment.parent_experiment_id),
                    ).fetchone()
                    if parent is None:
                        raise UnknownParentExperimentError(
                            f"parent experiment '{experiment.parent_experiment_id}' does not exist "
                            f"for run '{run_id}'"
                        )

                connection.execute(
                    """
                    INSERT INTO experiments (
                        run_id,
                        experiment_id,
                        parent_experiment_id,
                        payload
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        experiment.id,
                        experiment.parent_experiment_id,
                        experiment.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateRecordError(
                f"experiment '{experiment.id}' already exists for run '{run_id}'"
            ) from error

    def list_experiments(self, run_id: str) -> list[ExperimentSpec]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM experiments
                WHERE run_id = ?
                ORDER BY sequence ASC
                """,
                (run_id,),
            ).fetchall()
        return [ExperimentSpec.model_validate_json(row[0]) for row in rows]

    def create_approval(self, approval: ApprovalRecord) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO approvals (approval_id, payload)
                    VALUES (?, ?)
                    """,
                    (approval.id, approval.model_dump_json()),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateRecordError(f"approval '{approval.id}' already exists") from error

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        return None if row is None else ApprovalRecord.model_validate_json(row[0])

    def decide_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        reason: str | None,
    ) -> ApprovalRecord:
        if status not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise InvalidApprovalTransitionError("decision must be approved or rejected")

        approval = self.get_approval(approval_id)
        if approval is None:
            raise UnknownApprovalError(f"approval '{approval_id}' does not exist")
        if approval.status is not ApprovalStatus.PENDING:
            raise InvalidApprovalTransitionError(
                f"approval '{approval_id}' is already {approval.status.value}"
            )

        decided = approval.model_copy(
            update={
                "status": status,
                "decided_at": datetime.now(UTC),
                "reason": reason,
            }
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE approvals
                SET payload = ?
                WHERE approval_id = ? AND payload = ?
                """,
                (decided.model_dump_json(), approval_id, approval.model_dump_json()),
            )
            if cursor.rowcount != 1:
                raise InvalidApprovalTransitionError(
                    f"approval '{approval_id}' changed concurrently"
                )
        return decided

    def consume_approval(self, approval_id: str, scope_fingerprint: str) -> ApprovalRecord:
        approval = self.get_approval(approval_id)
        if approval is None:
            raise UnknownApprovalError(f"approval '{approval_id}' does not exist")
        if approval.scope_fingerprint != scope_fingerprint:
            raise InvalidApprovalTransitionError("approved scope fingerprint does not match")
        if approval.status is not ApprovalStatus.APPROVED:
            raise InvalidApprovalTransitionError(
                f"approval '{approval_id}' is {approval.status.value}, not approved"
            )

        consumed = approval.model_copy(update={"status": ApprovalStatus.CONSUMED})
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE approvals
                SET payload = ?
                WHERE approval_id = ? AND payload = ?
                """,
                (consumed.model_dump_json(), approval_id, approval.model_dump_json()),
            )
            if cursor.rowcount != 1:
                raise InvalidApprovalTransitionError(
                    f"approval '{approval_id}' changed concurrently"
                )
        return consumed

    def create_live_run(self, run_id: str, adapter: str) -> None:
        """Record a queued background execution before returning HTTP 202."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO live_runs (run_id, adapter, status, state) VALUES (?, ?, ?, ?)",
                (run_id, adapter, "queued", "awaiting_approval"),
            )
            connection.execute(
                "INSERT INTO run_events (run_id, state) VALUES (?, ?)",
                (run_id, "awaiting_approval"),
            )

    def record_run_state(self, run_id: str, state: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE live_runs SET status = 'running', state = ? WHERE run_id = ?",
                (state, run_id),
            )
            connection.execute(
                "INSERT INTO run_events (run_id, state) VALUES (?, ?)",
                (run_id, state),
            )

    def finish_live_run(self, run_id: str, result: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE live_runs SET status = 'completed', state = 'completed', "
                "result = ? WHERE run_id = ?",
                (json.dumps(result), run_id),
            )

    def fail_live_run(self, run_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE live_runs SET status = 'failed', state = 'failed', error = ? "
                "WHERE run_id = ?",
                (error[:1000], run_id),
            )
            connection.execute(
                "INSERT INTO run_events (run_id, state) VALUES (?, 'failed')",
                (run_id,),
            )

    def get_live_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT adapter, status, state, result, error FROM live_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            events = connection.execute(
                "SELECT state FROM run_events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return {
            "run_id": run_id,
            "adapter": row[0],
            "status": row[1],
            "state": row[2],
            "events": [event[0] for event in events],
            "result": json.loads(row[3]) if row[3] else None,
            "error": row[4],
        }

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE (run_id, evidence_id)
                );

                CREATE INDEX IF NOT EXISTS evidence_run_sequence
                    ON evidence (run_id, sequence);

                CREATE TABLE IF NOT EXISTS experiments (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    parent_experiment_id TEXT,
                    payload TEXT NOT NULL,
                    UNIQUE (run_id, experiment_id),
                    FOREIGN KEY (run_id, parent_experiment_id)
                        REFERENCES experiments (run_id, experiment_id)
                );

                CREATE INDEX IF NOT EXISTS experiment_run_sequence
                    ON experiments (run_id, sequence);

                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS live_runs (
                    run_id TEXT PRIMARY KEY,
                    adapter TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS run_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES live_runs (run_id)
                );
                """
            )
