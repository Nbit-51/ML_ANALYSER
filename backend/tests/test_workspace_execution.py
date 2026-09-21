"""Tests for isolated baseline/candidate workspace handling."""

from pathlib import Path

import pytest

from ml_analyser.execution.workspace import (
    IsolatedWorkspaceManager,
    WorkspaceIsolationError,
)


def test_candidate_changes_do_not_modify_source_and_can_be_discarded(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.json").write_text('{"value": 1}\n', encoding="utf-8")
    manager = IsolatedWorkspaceManager(tmp_path / "executions")

    handle = manager.create(run_id="run-1", label="candidate", source_root=source)
    (handle.workspace_root / "config.json").write_text('{"value": 2}\n', encoding="utf-8")

    assert (source / "config.json").read_text(encoding="utf-8") == '{"value": 1}\n'
    manager.discard(handle)
    assert not handle.workspace_root.exists()


def test_accepted_candidate_can_be_retained(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("print('fixture')\n", encoding="utf-8")
    manager = IsolatedWorkspaceManager(tmp_path / "executions")

    handle = manager.create(run_id="run-2", label="candidate", source_root=source)

    assert manager.retain(handle) == handle.workspace_root
    assert handle.workspace_root.is_dir()


def test_workspace_rejects_unsafe_run_identifier(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    manager = IsolatedWorkspaceManager(tmp_path / "executions")

    with pytest.raises(WorkspaceIsolationError, match="unsafe"):
        manager.create(run_id="../escape", label="candidate", source_root=source)
