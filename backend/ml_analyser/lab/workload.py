"""Synthetic multi-tenant pricing workload and an exact reference implementation.

The optimization changes cache configuration, not this evaluator or reference.
Work units count reference lookups, not milliseconds or estimated cloud cost.
"""

from __future__ import annotations

import hashlib
import random
from typing import Literal

from typing_extensions import TypedDict

CacheField = Literal["tenant", "sku", "currency"]
FIELDS: tuple[CacheField, ...] = ("tenant", "sku", "currency")


class Query(TypedDict):
    tenant: str
    sku: str
    currency: str


def quote(query: Query) -> int:
    """Return an integer price in minor currency units, scoped to all three fields."""
    identity = f"{query['tenant']}/{query['sku']}/{query['currency']}"
    return 100 + int(hashlib.sha256(identity.encode()).hexdigest()[:8], 16) % 100000


def workload(seed: int, *, discovery: bool = False) -> list[Query]:
    rng = random.Random(seed)
    tenants = ["tenant-a"] if discovery else [f"tenant-{rng.randrange(10**9)}" for _ in range(3)]
    currencies = ["USD"] if discovery else ["USD", "EUR"]
    products = [f"sku-{rng.randrange(10**9)}" for _ in range(5)]
    queries: list[Query] = [
        Query(tenant=tenant, sku=sku, currency=currency)
        for tenant in tenants
        for sku in products
        for currency in currencies
    ] * 4
    rng.shuffle(queries)
    return queries


def run(queries: list[Query], fields: list[CacheField]) -> tuple[int, list[int]]:
    """Execute the actual configured cache with a new empty cache for every round."""
    cache: dict[tuple[str, ...], int] = {}
    outputs: list[int] = []
    lookups = 0
    for query in queries:
        key = tuple(query[field] for field in fields)
        if not fields or key not in cache:
            price = quote(query)
            lookups += 1
            if fields:
                cache[key] = price
        else:
            price = cache[key]
        outputs.append(price)
    return lookups, outputs
