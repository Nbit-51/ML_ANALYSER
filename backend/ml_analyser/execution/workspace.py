"""Create and safely discard isolated experiment workspaces."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ml_analyser.tools.repository import RepositoryInventoryTool

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
COPY_IGNORE_PATTERNS = (
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "node_modules",
    "venv",
)


class WorkspaceIsolationError(ValueError):
    """Raised when a project cannot be copied into a safe experiment workspace."""


@dataclass(frozen=True, slots=True)
class WorkspaceHandle:
    run_id: str
    label: str
    source_root: Path
    workspace_root: Path
    source_fingerprint: str


class IsolatedWorkspaceManager:
    """Copy a project before execution and constrain cleanup to the execution root."""

    def __init__(self, execution_root: Path) -> None:
        self._execution_root = execution_root.resolve()

    def create(self, *, run_id: str, label: str, source_root: Path) -> WorkspaceHandle:
        self._validate_identifier(run_id, "run_id")
        self._validate_identifier(label, "label")
        source = source_root.resolve(strict=True)
        if not source.is_dir():
            raise WorkspaceIsolationError("source_root must be a directory")

        symlinks = sorted(
            path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_symlink()
        )
        if symlinks:
            raise WorkspaceIsolationError(
                f"source project contains unsupported symbolic link(s): {', '.join(symlinks[:5])}"
            )

        target = (self._execution_root / run_id / label).resolve()
        self._assert_managed_path(target)
        if target.exists():
            raise WorkspaceIsolationError(f"workspace already exists: {run_id}/{label}")

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns(*COPY_IGNORE_PATTERNS),
        )
        return WorkspaceHandle(
            run_id=run_id,
            label=label,
            source_root=source,
            workspace_root=target,
            source_fingerprint=self._fingerprint(source),
        )

    def discard(self, handle: WorkspaceHandle) -> None:
        target = handle.workspace_root.resolve(strict=True)
        self._assert_managed_path(target)
        expected_parent = (self._execution_root / handle.run_id).resolve()
        if target.parent != expected_parent:
            raise WorkspaceIsolationError("workspace handle does not match its run directory")
        shutil.rmtree(target)
        if expected_parent.exists() and not any(expected_parent.iterdir()):
            expected_parent.rmdir()

    def retain(self, handle: WorkspaceHandle) -> Path:
        """Keep an accepted candidate isolated for later, separately approved promotion."""
        target = handle.workspace_root.resolve(strict=True)
        self._assert_managed_path(target)
        return target

    def _assert_managed_path(self, path: Path) -> None:
        if path == self._execution_root:
            raise WorkspaceIsolationError("execution root itself cannot be an experiment workspace")
        try:
            path.relative_to(self._execution_root)
        except ValueError as error:
            raise WorkspaceIsolationError("workspace path escapes execution root") from error

    @staticmethod
    def _validate_identifier(identifier: str, field: str) -> None:
        if not SAFE_IDENTIFIER.fullmatch(identifier):
            raise WorkspaceIsolationError(f"{field} contains unsafe characters")

    @staticmethod
    def _fingerprint(root: Path) -> str:
        inventory = RepositoryInventoryTool().inspect(str(root))
        digest = sha256()
        for item in inventory.files:
            digest.update(item.path.encode("utf-8"))
            digest.update((item.sha256 or item.hash_status).encode("utf-8"))
        return digest.hexdigest()
