"""SQLite-backed append-only evidence ledger and experiment DAG."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ml_analyser.agent.models import EvidenceRecord, ExperimentSpec


class DuplicateRecordError(ValueError):
    """Raised when an append-only record identifier already exists."""


class UnknownParentExperimentError(ValueError):
    """Raised when a DAG node references a missing parent in the same run."""


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
                """
            )
