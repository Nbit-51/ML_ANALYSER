"""Stable identifier helpers for reproducible dry runs."""

import json
from hashlib import sha256

from pydantic import BaseModel


def stable_id(prefix: str, *parts: str) -> str:
    """Build a compact deterministic identifier from stable input parts."""
    digest = sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def model_fingerprint(model: BaseModel) -> str:
    """Hash a model's canonical JSON representation for approval integrity."""
    payload = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()
