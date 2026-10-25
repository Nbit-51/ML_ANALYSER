"""Atomic demo quotas, private precommitted seeds and browser-bound run storage."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class LabStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS lab_runs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, "
                "live INTEGER NOT NULL, created REAL NOT NULL, payload TEXT, result TEXT)"
            )

    def reserve(self, run_id: str, owner: str, *, live: bool, limit: int, cooldown: int) -> None:
        now = datetime.now(UTC)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            recent = db.execute(
                "SELECT MAX(created) FROM lab_runs WHERE owner = ?", (owner,)
            ).fetchone()[0]
            if recent is not None and now.timestamp() - recent < cooldown:
                raise ValueError("Please wait before preparing another campaign.")
            count = db.execute(
                "SELECT COUNT(*) FROM lab_runs WHERE created >= ? AND live = ?",
                (midnight, int(live)),
            ).fetchone()[0]
            if count >= (limit if live else 200):
                raise ValueError(
                    "The daily demo allowance is used. "
                    "Downloaded evidence can still be replayed offline."
                )
            db.execute(
                "INSERT INTO lab_runs (id, owner, live, created) VALUES (?, ?, ?, ?)",
                (run_id, owner, int(live), now.timestamp()),
            )

    def save_plan(self, run_id: str, payload: dict[str, Any]) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "UPDATE lab_runs SET payload = ? WHERE id = ?", (json.dumps(payload), run_id)
            )

    def load(self, run_id: str, owner: str) -> dict[str, Any]:
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute(
                "SELECT payload, created FROM lab_runs WHERE id = ? AND owner = ?", (run_id, owner)
            ).fetchone()
        if row is None or row[0] is None:
            raise ValueError("Campaign not found in this browser session.")
        if datetime.now(UTC).timestamp() - row[1] > 900:
            raise ValueError("This preparation expired. Prepare a new campaign.")
        return dict(json.loads(row[0]))

    def finish(self, run_id: str, report: dict[str, Any]) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE lab_runs SET result = ? WHERE id = ?", (json.dumps(report), run_id))
