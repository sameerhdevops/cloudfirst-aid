"""Evidence handling — loading fixtures, collecting local data, provenance tracking.

Evidence is the bridge between a symptom and a finding. This module loads
evidence fixtures (simulated data shipped with the project), and can
optionally collect basic local system data for comparison.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cloudfirst_aid.models import EvidenceItem

_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


def load_evidence_fixtures(scenario_id: str, fixtures_dir: Path | None = None) -> list[EvidenceItem]:
    """Load simulated evidence for a scenario from its fixture file.

    Fixture files are named like: evidence_CFA-001.json
    Each contains a list of evidence item dictionaries.
    """
    base = fixtures_dir or _FIXTURES_DIR
    fixture_file = base / f"evidence_{scenario_id}.json"

    if not fixture_file.exists():
        return []

    with open(fixture_file, encoding="utf-8") as f:
        items: list[dict[str, Any]] = json.load(f)

    return [EvidenceItem.from_dict(item) for item in items]


def format_evidence_record(item: EvidenceItem) -> str:
    """Format a single evidence item for display or report inclusion."""
    lines = [
        f"Evidence: {item.id}",
        f"  Description: {item.description}",
        f"  Source:      {item.source}",
        f"  Provenance:  {item.provenance}",
    ]
    if item.observation:
        # Indent multi-line observations
        obs_lines = item.observation.strip().split("\n")
        lines.append("  Observation:")
        for ol in obs_lines:
            lines.append(f"    {ol}")
    if item.limitations:
        lines.append(f"  Limitations: {item.limitations}")
    if item.collected_at:
        lines.append(f"  Collected:   {item.collected_at}")
    return "\n".join(lines)


def redact_sensitive_fields(text: str) -> str:
    """Basic redaction of common sensitive patterns in evidence text.

    Replaces AWS access key IDs, secret keys, and account-ID-like
    12-digit numbers. This is a safety net, not a substitute for
    careful evidence design.
    """
    import re

    # AWS Access Key ID pattern (AKIA...)
    text = re.sub(r"AKIA[0-9A-Z]{16}", "AKIA****************", text)
    # Long base64-like secret keys (40 chars)
    text = re.sub(r"(?<=['\"\s=])[A-Za-z0-9/+=]{40}(?=['\"\s,])", "[REDACTED]", text)
    # 12-digit AWS account IDs
    text = re.sub(r"\b\d{12}\b", "************", text)
    return text


def summarize_evidence(items: list[EvidenceItem]) -> dict[str, list[EvidenceItem]]:
    """Group evidence items by provenance category."""
    groups: dict[str, list[EvidenceItem]] = {
        "simulated": [],
        "local": [],
        "live_aws": [],
    }
    for item in items:
        bucket = groups.get(item.provenance, groups["simulated"])
        bucket.append(item)
    return groups
