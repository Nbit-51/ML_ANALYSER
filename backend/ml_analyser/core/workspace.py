"""Workspace path validation for locally submitted projects."""

from pathlib import Path


class InvalidWorkspacePath(ValueError):
    """Raised when a requested project escapes the configured workspace."""


def resolve_project_path(workspace_root: Path, requested_path: str) -> Path:
    """Resolve a project directory while preventing absolute paths and traversal."""
    relative = Path(requested_path)
    if not requested_path.strip() or relative.is_absolute():
        raise InvalidWorkspacePath("project_path must be a non-empty relative path")

    root = workspace_root.resolve(strict=True)
    candidate = (root / relative).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise InvalidWorkspacePath("project_path must stay inside the workspace") from error

    if candidate == root or not candidate.is_dir():
        raise InvalidWorkspacePath("project_path must identify a project directory")
    return candidate
