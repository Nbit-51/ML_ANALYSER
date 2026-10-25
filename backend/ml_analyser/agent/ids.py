"""Stable identifier helpers for reproducible dry runs."""

import json
from hashlib import sha256
from typing import Any

from pydantic import BaseModel


def stable_id(prefix: str, *parts: str) -> str:
    """Build a compact deterministic identifier from stable input parts."""
    digest = sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def model_fingerprint(model: BaseModel) -> str:
    """Hash a model's canonical JSON representation for approval integrity."""
    return sha256(canonical_json(model.model_dump(mode="json")).encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    """Serialize JSON with equivalent whole-number representations normalized."""
    return json.dumps(
        _canonical_numbers(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _canonical_numbers(value: Any) -> Any:
    """JSON has one numeric type; browser serialization renders 0.0 as 0.

    Preserve booleans, strings and all numeric values while removing that
    representational distinction. Source bytes are fingerprinted separately.
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical_numbers(item) for item in value]
    return value
