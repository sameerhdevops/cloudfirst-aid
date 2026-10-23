"""Pytest configuration and shared test fixtures for CloudFirst Aid."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/ is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from cloudfirst_aid.catalog import load_catalog  # noqa: E402
from cloudfirst_aid.models import Scenario  # noqa: E402


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def catalog(project_root: Path) -> list[Scenario]:
    """Load the full scenario catalog once for the test session."""
    return load_catalog(project_root / "scenarios" / "catalog")
