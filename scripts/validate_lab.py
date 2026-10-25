"""Small live check: feed actual counterexamples to Nebius and measure its revision."""

import asyncio
import secrets

from ml_analyser.core.config import get_settings
from ml_analyser.lab.engine import LabReasoner, Proposal, measure


async def main() -> None:
    settings = get_settings()
    if settings.model_provider != "nebius":
        raise ValueError("Select the live Nebius provider before this explicit inference check.")
    seed = secrets.token_hex(24)
    control = measure(
        Proposal(
            cache_fields=["sku"], rationale="Declared unsafe control for feedback validation."
        ),
        seed,
        1,
    )
    assert control.decision.status == "rejected" and control.counterexamples
    reasoner = LabReasoner(settings)
    proposal = await reasoner.propose([control])
    revision = measure(proposal, seed, 2)
    print("Provider:", reasoner.name)
    print("Measured control errors:", control.candidate.incorrect_quotes)
    print("Revised fields:", ", ".join(proposal.cache_fields))
    print("Revision decision:", revision.decision.status.value)
    print(
        "Reference lookups:",
        revision.baseline.reference_lookups,
        "->",
        revision.candidate.reference_lookups,
    )
    print("Revision errors:", revision.candidate.incorrect_quotes)
    print("Model calls/tokens:", reasoner.calls, reasoner.tokens)
    if revision.decision.status != "accepted":
        raise ValueError("No accepted live revision; inspect the provider configuration.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Live lab validation failed: {type(error).__name__}: {error}")
        raise SystemExit(1) from None
