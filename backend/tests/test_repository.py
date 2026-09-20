"""Tests for bounded, read-only repository inventory and state graph creation."""

from pathlib import Path

from ml_analyser.agent.models import FileCategory, GraphNodeType
from ml_analyser.agent.state_graph import InventoryStateGraphBuilder
from ml_analyser.tools.repository import RepositoryInventoryTool


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_inventory_classifies_files_and_ignores_environment(tmp_path: Path) -> None:
    _write(tmp_path / "train.py", "print('not executed')\n")
    _write(tmp_path / "tests" / "test_train.py", "def test_placeholder(): pass\n")
    _write(tmp_path / "config.yaml", "epochs: 1\n")
    _write(tmp_path / "metrics.json", '{"f1": 0.5}\n')
    _write(tmp_path / ".venv" / "ignored.py", "raise RuntimeError\n")

    inventory = RepositoryInventoryTool().inspect(str(tmp_path))

    categories = {item.path: item.category for item in inventory.files}
    assert categories == {
        "config.yaml": FileCategory.CONFIGURATION,
        "metrics.json": FileCategory.METRICS,
        "tests/test_train.py": FileCategory.TEST,
        "train.py": FileCategory.SOURCE,
    }
    assert all(item.sha256 for item in inventory.files)
    assert inventory.total_files == 4


def test_inventory_respects_file_and_hash_limits(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "12345")
    _write(tmp_path / "b.py", "67890")

    inventory = RepositoryInventoryTool(max_files=1, max_hash_bytes=2).inspect(str(tmp_path))

    assert inventory.total_files == 1
    assert inventory.files[0].sha256 is None
    assert inventory.files[0].hash_status == "skipped:size_limit"
    assert inventory.skipped_paths == ["b.py:file_limit"]


def test_state_graph_is_deterministic(tmp_path: Path) -> None:
    _write(tmp_path / "model.py", "class Model: pass\n")
    inventory = RepositoryInventoryTool().inspect(str(tmp_path))
    builder = InventoryStateGraphBuilder()

    first = builder.build("sample", inventory)
    second = builder.build("sample", inventory)

    assert first == second
    assert [node.type for node in first.nodes].count(GraphNodeType.PROJECT) == 1
    assert [node.type for node in first.nodes].count(GraphNodeType.FILE) == 1
