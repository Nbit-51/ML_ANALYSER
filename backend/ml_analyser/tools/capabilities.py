"""Conservative capability facts; filenames are evidence, not execution results."""

from collections import Counter
from pathlib import Path, PurePosixPath

from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import (
    Capability,
    EvidenceKind,
    EvidenceRecord,
    RepositoryInventory,
    RepositorySummary,
)
from ml_analyser.tools.repository_context import RepositoryContextTool

BUILD_FILES = {
    "pyproject.toml": "Python packaging",
    "setup.py": "Python packaging",
    "requirements.txt": "pip",
    "package.json": "Node",
    "cmakelists.txt": "CMake",
    "makefile": "Make",
    "cargo.toml": "Cargo",
    "go.mod": "Go modules",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
    "pom.xml": "Maven",
}


def detect_capabilities(
    inventory: RepositoryInventory,
) -> tuple[RepositorySummary, list[EvidenceRecord]]:
    facts: list[Capability] = []
    evidence: list[EvidenceRecord] = []
    languages: Counter[str] = Counter()
    for item in inventory.files:
        if item.language:
            languages[item.language] += item.size_bytes
        path = PurePosixPath(item.path)
        name = path.name.lower()
        matches: list[tuple[str, str, str]] = []
        if name in BUILD_FILES:
            matches.append((BUILD_FILES[name], "build_system", "detected"))
            contents = RepositoryContextTool._read(Path(inventory.project_root), item.path, 32768)
            if contents:
                text, _ = contents
                for token, kind in (
                    ("pytest", "test_system"),
                    ("jest", "test_system"),
                    ("vitest", "test_system"),
                    ("torch", "ml"),
                    ("tensorflow", "ml"),
                    ("scikit-learn", "ml"),
                    ("fastapi", "web"),
                    ("express", "web"),
                    ("criterion", "benchmark"),
                    ("benchmark", "benchmark"),
                ):
                    if token in text.lower():
                        matches.append(
                            (f"{token} reference in build configuration", kind, "inferred")
                        )
        if name.startswith(("pytest", "jest.config", "vitest.config")) or item.category == "test":
            matches.append(("Test configuration / suite", "test_system", "detected"))
        if "bench" in item.path.lower():
            matches.append(("Benchmark definition", "benchmark", "inferred"))
        if name.startswith("dockerfile"):
            matches.append(("Docker", "container", "detected"))
        if item.path.startswith(".github/workflows/") or name in {".gitlab-ci.yml", "jenkinsfile"}:
            matches.append(("CI workflow", "ci", "detected"))
        if name in {"main.py", "app.py", "main.go", "main.rs", "index.js", "train.py"}:
            matches.append(("Likely entrypoint", "entrypoint", "inferred"))
        if "train" in name or item.category == "model_artifact":
            matches.append(("ML indicators", "ml", "inferred"))
        if any(token in name for token in ("server", "route", "api")):
            matches.append(("Web/API indicators", "web", "inferred"))
        if item.category in {"configuration", "data", "model_artifact", "metrics", "documentation"}:
            matches.append((item.category.value.replace("_", " "), item.category.value, "detected"))
        if name in {"repo_benchmark.json", "ml_experiment.json", "backend_benchmark.json"}:
            matches.append(("Benchmark manifest (validation required)", "manifest", "detected"))
        if not matches:
            continue
        record = EvidenceRecord(
            id=stable_id("evidence", "capability", item.path, item.sha256 or item.hash_status),
            kind=EvidenceKind.INVENTORY,
            source=item.path,
            content_hash=item.sha256,
            claim=f"Inspected {item.path}; bounded static indicators only, not executed.",
        )
        evidence.append(record)
        for label, kind, provenance in matches:
            facts.append(
                Capability(
                    id=stable_id("capability", item.path, kind, label),
                    name=label,
                    kind=kind,
                    provenance=provenance,
                    confidence=0.6 if provenance == "inferred" else 1,
                    evidence_ids=[record.id],
                    paths=[item.path],
                )
            )
    return RepositorySummary(
        language_bytes=dict(sorted(languages.items())), capabilities=facts
    ), evidence
