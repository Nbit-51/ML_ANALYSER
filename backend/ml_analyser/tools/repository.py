"""Read-only, bounded repository inventory."""

from __future__ import annotations

import os
from collections import Counter
from hashlib import sha256
from pathlib import Path

from ml_analyser.agent.models import FileCategory, InventoryFile, RepositoryInventory

DEFAULT_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)

SOURCE_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".php": "php",
    ".py": "python",
    ".r": "r",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "shell",
    ".sql": "sql",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
}

CONFIGURATION_SUFFIXES = frozenset({".ini", ".json", ".toml", ".yaml", ".yml"})
DATA_SUFFIXES = frozenset({".csv", ".feather", ".parquet", ".tsv"})
MODEL_SUFFIXES = frozenset({".ckpt", ".joblib", ".onnx", ".pt", ".pth", ".safetensors"})
METRIC_NAMES = frozenset(
    {"eval_results.json", "evaluation.json", "metrics.csv", "metrics.json", "results.json"}
)
DOCUMENTATION_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt"})


class RepositoryInventoryError(ValueError):
    """Raised when a repository cannot be safely inventoried."""


class RepositoryInventoryTool:
    """Build metadata without executing or semantically importing project code."""

    def __init__(
        self,
        *,
        max_files: int = 5_000,
        max_hash_bytes: int = 5 * 1024 * 1024,
        ignored_directories: frozenset[str] = DEFAULT_IGNORED_DIRECTORIES,
    ) -> None:
        if max_files < 1:
            raise ValueError("max_files must be positive")
        if max_hash_bytes < 1:
            raise ValueError("max_hash_bytes must be positive")
        self._max_files = max_files
        self._max_hash_bytes = max_hash_bytes
        self._ignored_directories = ignored_directories

    def inspect(self, project_root: str) -> RepositoryInventory:
        root = Path(project_root).resolve(strict=True)
        if not root.is_dir():
            raise RepositoryInventoryError("project root must be a directory")

        files: list[InventoryFile] = []
        skipped: list[str] = []

        for current_root, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current_root)
            directories[:] = sorted(
                directory
                for directory in directories
                if directory not in self._ignored_directories
                and not (current_path / directory).is_symlink()
            )

            for filename in sorted(filenames):
                path = current_path / filename
                relative = path.relative_to(root).as_posix()

                if len(files) >= self._max_files:
                    skipped.append(f"{relative}:file_limit")
                    continue
                if path.is_symlink():
                    skipped.append(f"{relative}:symlink")
                    continue

                try:
                    stat = path.stat()
                except OSError as error:
                    skipped.append(f"{relative}:stat_error:{type(error).__name__}")
                    continue

                digest: str | None = None
                hash_status = "complete"
                if stat.st_size <= self._max_hash_bytes:
                    try:
                        digest = self._hash_file(path)
                    except OSError as error:
                        hash_status = f"error:{type(error).__name__}"
                else:
                    hash_status = "skipped:size_limit"

                category, language = self._classify(path, relative)
                files.append(
                    InventoryFile(
                        path=relative,
                        size_bytes=stat.st_size,
                        category=category,
                        language=language,
                        sha256=digest,
                        hash_status=hash_status,
                    )
                )

        files.sort(key=lambda item: item.path)
        counts = Counter(item.category.value for item in files)
        return RepositoryInventory(
            project_root=str(root),
            files=files,
            skipped_paths=skipped,
            total_files=len(files),
            total_bytes=sum(item.size_bytes for item in files),
            category_counts=dict(sorted(counts.items())),
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _classify(path: Path, relative_path: str) -> tuple[FileCategory, str | None]:
        suffix = path.suffix.casefold()
        name = path.name.casefold()
        parts = {part.casefold() for part in Path(relative_path).parts}

        if suffix == ".ipynb":
            return FileCategory.NOTEBOOK, "jupyter"
        if "test" in parts or "tests" in parts or name.startswith("test_"):
            return FileCategory.TEST, SOURCE_LANGUAGES.get(suffix)
        if name in METRIC_NAMES or "metric" in name or "result" in name:
            return FileCategory.METRICS, None
        if suffix in MODEL_SUFFIXES:
            return FileCategory.MODEL_ARTIFACT, None
        if suffix in DATA_SUFFIXES:
            return FileCategory.DATA, None
        if suffix in SOURCE_LANGUAGES:
            return FileCategory.SOURCE, SOURCE_LANGUAGES[suffix]
        if suffix in CONFIGURATION_SUFFIXES or name in {"dockerfile", "makefile"}:
            return FileCategory.CONFIGURATION, None
        if suffix in DOCUMENTATION_SUFFIXES:
            return FileCategory.DOCUMENTATION, None
        return FileCategory.OTHER, None
