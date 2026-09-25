"""Bounded, read-only excerpts for evidence-based repository previews."""

from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import (
    EvidenceKind,
    EvidenceRecord,
    FileCategory,
    RepositoryInventory,
    SuccessContract,
)

MAX_FILE_BYTES = 128 * 1024
MAX_RESULT_BYTES = 64 * 1024
MAX_EXCERPT_CHARS = 1_600


class RepositoryContextTool:
    """Read a few relevant text artifacts without importing repository code."""

    def collect(
        self, project_root: Path, inventory: RepositoryInventory, contract: SuccessContract
    ) -> list[EvidenceRecord]:
        root = project_root.resolve(strict=True)
        metric = contract.objective.metric
        metrics = [metric, *(constraint.metric for constraint in contract.constraints)]
        by_path = {item.path: item for item in inventory.files}
        evidence: list[EvidenceRecord] = []

        readme = by_path.get("README.md") or by_path.get("readme.md")
        if readme is not None:
            contents = self._read(root, readme.path, MAX_FILE_BYTES)
            if contents is not None:
                text, digest = contents
                excerpt = self._readme_excerpt(text, metric)
                evidence.append(
                    self._record(
                        readme.path,
                        digest,
                        (
                            "Repository README excerpt (documentation, not a verified result): "
                            f"{excerpt}"
                        ),
                    )
                )

        matched_results: list[tuple[str, dict[str, float], str, str]] = []
        for item in inventory.files:
            path = Path(item.path)
            if path.suffix.casefold() != ".json" or not {part.casefold() for part in path.parts} & {
                "benchmark",
                "benchmarks",
                "results",
                "metrics",
            }:
                continue
            contents = self._read(root, item.path, MAX_RESULT_BYTES)
            if contents is None:
                continue
            text, digest = contents
            try:
                payload = json.loads(text)
            except ValueError:
                continue
            values = {
                name: value
                for name in metrics
                if (value := self._find_metric(payload, name)) is not None
            }
            if metric in values:
                matched_results.append((item.path, values, text, digest))

        matched_results.sort(key=lambda item: (-len(item[1]), item[0]))
        for result_path, values, text, digest in matched_results[:2]:
            reported = ", ".join(f"{name}={value:g}" for name, value in values.items())
            evidence.append(
                self._record(
                    result_path,
                    digest,
                    (
                        f"Repository result file reports {reported}; this is a prior "
                        f"record, not a measurement made by this preview. Context: "
                        f"{text[:MAX_EXCERPT_CHARS]}"
                    ),
                    metrics_json=json.dumps(values, sort_keys=True),
                )
            )

        # Rank by overlap with the requested metric and matching result filenames,
        # without assuming the repository is a classifier, trainer, or inference engine.
        context_tokens = set(self._tokens(metric))
        for result_path, *_ in matched_results[:2]:
            context_tokens.update(self._tokens(Path(result_path).stem))
        source_candidates = sorted(
            (
                item
                for item in inventory.files
                if item.category is FileCategory.SOURCE
                and Path(item.path).stem.casefold() != "__init__"
            ),
            key=lambda item: (
                -len(context_tokens.intersection(self._tokens(item.path))),
                -min(item.size_bytes, 10_000),
                item.path,
            ),
        )
        for item in source_candidates[:2]:
            contents = self._read(root, item.path, MAX_FILE_BYTES)
            if contents is not None:
                text, digest = contents
                evidence.append(
                    self._record(
                        item.path,
                        digest,
                        f"Source excerpt (partial file, not executed): {text[:MAX_EXCERPT_CHARS]}",
                    )
                )
        return evidence

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) >= 3}

    @staticmethod
    def _read(root: Path, relative_path: str, max_bytes: int) -> tuple[str, str] | None:
        try:
            path = (root / relative_path).resolve(strict=True)
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or path.stat().st_size > max_bytes
            ):
                return None
            contents = path.read_bytes()
        except OSError:
            return None
        if b"\x00" in contents:
            return None
        return contents.decode("utf-8", errors="replace"), sha256(contents).hexdigest()

    @staticmethod
    def _find_metric(payload: Any, metric: str) -> float | None:
        if isinstance(payload, dict):
            value = payload.get(metric)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric = float(value)
                if math.isfinite(numeric):
                    return numeric
            for child in payload.values():
                found = RepositoryContextTool._find_metric(child, metric)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for child in payload:
                found = RepositoryContextTool._find_metric(child, metric)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _readme_excerpt(text: str, metric: str) -> str:
        terms = {part for part in metric.casefold().split("_") if len(part) >= 3}
        relevant = [
            line.strip()
            for line in text.splitlines()
            if any(term in line.casefold() for term in terms)
        ][:12]
        return (text[:700] + "\nRelevant lines:\n" + "\n".join(relevant))[:MAX_EXCERPT_CHARS]

    @staticmethod
    def _record(
        path: str, digest: str, claim: str, *, metrics_json: str | None = None
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=stable_id("evidence", "repository-context", path, digest),
            kind=EvidenceKind.SOURCE,
            claim=claim,
            source=path,
            content_hash=digest,
            metadata={"recorded_metrics_json": metrics_json} if metrics_json else {},
        )
