"""Opaque server-side sessions and account-scoped workspace settings."""

import hashlib
import secrets
import shutil
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ml_analyser.core.config import Settings


class AuthStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS sessions "
                "(digest TEXT PRIMARY KEY, user_id TEXT, login TEXT, expires REAL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS oauth_states "
                "(digest TEXT PRIMARY KEY, verifier TEXT, expires REAL)"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def begin(self) -> tuple[str, str]:
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        with self.connect() as db:
            db.execute("DELETE FROM oauth_states WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT INTO oauth_states VALUES (?, ?, ?)",
                (self.digest(state), verifier, time.time() + 600),
            )
        return state, verifier

    def consume(self, state: str) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "DELETE FROM oauth_states WHERE digest = ? RETURNING verifier, expires",
                (self.digest(state),),
            ).fetchone()
        return str(row[0]) if row and row[1] > time.time() else None

    def create(self, user_id: str, login: str) -> str:
        token = secrets.token_urlsafe(48)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)",
                (self.digest(token), user_id, login, time.time() + 28800),
            )
        return token

    def user(self, token: str) -> dict[str, str] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT user_id, login FROM sessions WHERE digest = ? AND expires > ?",
                (self.digest(token), time.time()),
            ).fetchone()
        return {"id": str(row[0]), "login": str(row[1])} if row else None

    def revoke(self, token: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE digest = ?", (self.digest(token),))


def account_settings(settings: Settings, user_id: str) -> Settings:
    # GitHub's numeric account ID, never a client-provided path or mutable login.
    if not user_id.isdecimal():
        raise ValueError("Invalid account ID")
    root = settings.auth_database.parent / "accounts" / user_id
    return settings.model_copy(
        update={
            "workspace_root": root / "workspaces",
            "execution_root": root / "executions",
            "state_database": root / "runs.db",
        }
    )


def seed_demos(settings: Settings) -> None:
    source = Path(__file__).resolve().parents[3] / "workspaces"
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    for name in ("ml-training-demo", "backend-benchmark-demo", "cli-benchmark-demo"):
        target = settings.workspace_root / name
        if not target.exists() and (source / name).is_dir():
            shutil.copytree(
                source / name,
                target,
                ignore=shutil.ignore_patterns("__pycache__", ".env*", "*.pyc"),
            )
