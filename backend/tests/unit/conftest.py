"""Unit-test scope: no database, no network, no provider.

The package-level `clean_database_and_storage` fixture in `tests/conftest.py` needs a live
PostgreSQL. These tests exercise pure extraction, grounding, scoring and routing logic, so the
fixture is shadowed here by a no-op of the same name.
"""

import pytest


@pytest.fixture(autouse=True)
def clean_database_and_storage():
    yield
