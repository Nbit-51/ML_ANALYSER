"""Keep automated tests independent of a developer's local provider credentials."""

from collections.abc import Iterator

import pytest

from ml_analyser.core.config import get_settings


@pytest.fixture(autouse=True)
def use_offline_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ML_ANALYSER_MODEL_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
