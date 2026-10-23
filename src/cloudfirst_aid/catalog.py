"""Scenario catalog loader and validator.

Loads scenario JSON files from the catalog directory, validates required
fields and identifier uniqueness, and provides lookup by ID or category.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cloudfirst_aid.models import Scenario

# Default catalog location: <project_root>/scenarios/catalog/
_DEFAULT_CATALOG_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios" / "catalog"


def _find_catalog_dir() -> Path:
    """Locate the scenario catalog directory.

    Checks, in order:
    1. The path relative to the installed package (for development).
    2. The current working directory's scenarios/catalog/.
    """
    if _DEFAULT_CATALOG_DIR.is_dir():
        return _DEFAULT_CATALOG_DIR

    cwd_catalog = Path.cwd() / "scenarios" / "catalog"
    if cwd_catalog.is_dir():
        return cwd_catalog

    raise FileNotFoundError(
        f"Scenario catalog not found. Checked:\n"
        f"  {_DEFAULT_CATALOG_DIR}\n"
        f"  {cwd_catalog}\n"
        f"Run this command from the cloudfirst-aid project root."
    )


def load_scenario_file(path: Path) -> dict[str, Any]:
    """Load and parse a single scenario JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_catalog(catalog_dir: Path | None = None) -> list[Scenario]:
    """Load all scenarios from JSON files in the catalog directory.

    Returns a list of Scenario objects sorted by ID.
    """
    catalog_path = catalog_dir or _find_catalog_dir()
    scenarios: list[Scenario] = []

    for json_file in sorted(catalog_path.glob("*.json")):
        try:
            data = load_scenario_file(json_file)
            scenario = Scenario.from_dict(data)
            scenarios.append(scenario)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"Error loading {json_file.name}: {exc}") from exc

    return scenarios


def get_scenario_by_id(scenarios: list[Scenario], scenario_id: str) -> Scenario | None:
    """Find a scenario by its unique identifier (case-insensitive)."""
    target = scenario_id.upper()
    for s in scenarios:
        if s.id.upper() == target:
            return s
    return None


def list_categories(scenarios: list[Scenario]) -> list[str]:
    """Return sorted unique category names."""
    return sorted({s.category for s in scenarios})


def filter_by_category(scenarios: list[Scenario], category: str) -> list[Scenario]:
    """Return scenarios matching a category (case-insensitive)."""
    target = category.lower()
    return [s for s in scenarios if s.category.lower() == target]


def validate_catalog(scenarios: list[Scenario]) -> list[str]:
    """Check the catalog for structural problems.

    Returns a list of error messages. An empty list means valid.
    """
    errors: list[str] = []

    if not scenarios:
        errors.append("Catalog is empty — no scenario files found.")
        return errors

    # Check for duplicate IDs
    seen_ids: dict[str, int] = {}
    for s in scenarios:
        if s.id in seen_ids:
            errors.append(f"Duplicate scenario ID: {s.id}")
        seen_ids[s.id] = seen_ids.get(s.id, 0) + 1

    # Check required fields on each scenario
    for s in scenarios:
        prefix = f"[{s.id}]"
        if not s.title.strip():
            errors.append(f"{prefix} Missing title.")
        if not s.category.strip():
            errors.append(f"{prefix} Missing category.")
        if not s.symptom.strip():
            errors.append(f"{prefix} Missing symptom description.")
        if not s.possible_causes:
            errors.append(f"{prefix} No possible causes defined.")
        if not s.investigation_steps:
            errors.append(f"{prefix} No investigation steps defined.")

        # Validate ID format (CFA-NNN)
        if not s.id.startswith("CFA-") or not s.id[4:].isdigit():
            errors.append(f"{prefix} ID does not match CFA-NNN format.")

        # Check difficulty and severity are recognized values
        valid_difficulties = {"beginner", "intermediate", "advanced"}
        if s.difficulty not in valid_difficulties:
            errors.append(f"{prefix} Unrecognized difficulty: {s.difficulty}")

        valid_severities = {"critical", "high", "medium", "low"}
        if s.severity not in valid_severities:
            errors.append(f"{prefix} Unrecognized severity: {s.severity}")

        # Check investigation step ordering
        orders = [step.order for step in s.investigation_steps]
        if orders != sorted(orders):
            errors.append(f"{prefix} Investigation steps are not in order.")
        if len(orders) != len(set(orders)):
            errors.append(f"{prefix} Duplicate step order numbers.")

    return errors
