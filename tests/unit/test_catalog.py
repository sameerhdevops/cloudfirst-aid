"""Unit tests for catalog loading, parsing, and validation."""

from __future__ import annotations

from cloudfirst_aid.catalog import (
    filter_by_category,
    get_scenario_by_id,
    list_categories,
    validate_catalog,
)
from cloudfirst_aid.models import Scenario


def test_catalog_loads_scenarios(catalog: list[Scenario]) -> None:
    """Verify catalog loads expected number of scenarios."""
    assert len(catalog) == 30
    assert all(isinstance(s, Scenario) for s in catalog)


def test_scenario_ids_are_unique(catalog: list[Scenario]) -> None:
    """Verify every scenario has a unique CFA-NNN identifier."""
    ids = [s.id for s in catalog]
    assert len(ids) == len(set(ids)), "Duplicate scenario IDs detected!"


def test_scenario_id_format(catalog: list[Scenario]) -> None:
    """Verify all IDs conform to CFA-NNN standard."""
    for s in catalog:
        assert s.id.startswith("CFA-"), f"Invalid ID format: {s.id}"
        assert s.id[4:].isdigit(), f"ID suffix is not digits: {s.id}"


def test_catalog_validation_passes(catalog: list[Scenario]) -> None:
    """Verify the production catalog passes all validation checks."""
    errors = validate_catalog(catalog)
    assert errors == [], f"Validation errors: {errors}"


def test_catalog_validation_detects_duplicates() -> None:
    """Verify validator catches duplicate IDs."""
    data = {
        "id": "CFA-001",
        "title": "Dup Test",
        "category": "ec2",
        "symptom": "Broken",
        "possible_causes": [{"cause": "X", "likelihood": "common", "evidence_needed": "E", "remediation": "R"}],
        "investigation_steps": [{"order": 1, "title": "S1", "command": "c", "explanation": "e", "what_to_look_for": "w"}],
    }
    s1 = Scenario.from_dict(data)
    s2 = Scenario.from_dict(data)
    errors = validate_catalog([s1, s2])
    assert any("Duplicate scenario ID" in err for err in errors)


def test_get_scenario_by_id(catalog: list[Scenario]) -> None:
    """Verify scenario lookup by ID (case-insensitive)."""
    s = get_scenario_by_id(catalog, "CFA-001")
    assert s is not None
    assert s.id == "CFA-001"
    assert "SSH" in s.title

    # Case-insensitive test
    s_lower = get_scenario_by_id(catalog, "cfa-001")
    assert s_lower is not None
    assert s_lower.id == "CFA-001"

    # Unknown ID test
    assert get_scenario_by_id(catalog, "CFA-999") is None


def test_list_and_filter_categories(catalog: list[Scenario]) -> None:
    """Verify category filtering and enumeration."""
    categories = list_categories(catalog)
    expected_categories = {"application", "ec2", "iam-s3", "linux", "monitoring", "networking"}
    assert set(categories) == expected_categories

    ec2_scenarios = filter_by_category(catalog, "ec2")
    assert len(ec2_scenarios) >= 4
    assert all(s.category == "ec2" for s in ec2_scenarios)
