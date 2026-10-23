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
        f"Evidence: {redact_sensitive_fields(item.id)}",
        f"  Description: {redact_sensitive_fields(item.description)}",
        f"  Source:      {redact_sensitive_fields(item.source)}",
        f"  Provenance:  {item.provenance}",
    ]
    if item.observation:
        # Indent multi-line observations after redaction
        sanitized_obs = redact_sensitive_fields(item.observation.strip())
        obs_lines = sanitized_obs.split("\n")
        lines.append("  Observation:")
        for ol in obs_lines:
            lines.append(f"    {ol}")
    if item.limitations:
        lines.append(f"  Limitations: {redact_sensitive_fields(item.limitations)}")
    if item.collected_at:
        lines.append(f"  Collected:   {redact_sensitive_fields(item.collected_at)}")
    return "\n".join(lines)


def redact_sensitive_fields(text: str) -> str:
    """Redact common sensitive patterns in evidence text.

    Replaces AWS access key IDs (standard and temporary), secret keys,
    bearer tokens, private key blocks, passwords, and 12-digit account IDs.
    Preserves legitimate 40-character Git commit hashes and file hashes.
    """
    import re

    if not text:
        return text

    # 1. Complete PEM private key blocks (RSA, EC, OPENSSH, DSA, or unadorned)
    text = re.sub(
        r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY BLOCK]",
        text,
    )

    # 2. AWS Access Key IDs (AKIA for permanent credentials, ASIA for temporary STS credentials)
    text = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "AKIA****************", text)
    text = re.sub(r"\bASIA[0-9A-Z]{16}\b", "ASIA****************", text)

    # 3. HTTP Authorization / Bearer tokens
    text = re.sub(
        r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/-]{16,}\b",
        r"\g<1>[REDACTED TOKEN]",
        text,
    )
    text = re.sub(
        r"(?i)\b(authorization:\s*)(?:basic|bearer|token)\s+[A-Za-z0-9._~+/-]+=*",
        r"\g<1>[REDACTED AUTH HEADER]",
        text,
    )

    # 4. Explicit password / secret assignment patterns
    text = re.sub(
        r"(?i)\b((?:password|passwd|pwd|secret_key|secret_access_key)\s*[:=]\s*['\"]?)(?:[^\s'\";]+)(['\"]?)",
        r"\g<1>[REDACTED]\g<2>",
        text,
    )

    # 5. Base64-like secret keys (40 chars), distinguishing them from 40-character Git commit hex hashes
    def _redact_secret_key(match: re.Match[str]) -> str:
        candidate = match.group(0)
        # Preserve Git commit hashes (strictly 40 lowercase hexadecimal characters) and 64-char sha256
        if re.fullmatch(r"[0-9a-f]{40}", candidate) or re.fullmatch(r"[0-9a-f]{64}", candidate):
            return candidate
        return "[REDACTED]"

    text = re.sub(r"(?<=['\"\s=:])([A-Za-z0-9/+=]{40})(?=['\"\s,;]|$)", _redact_secret_key, text)

    # 6. 12-digit AWS account IDs (standalone digits)
    text = re.sub(r"(?<=\b)\d{12}(?=\b)", "************", text)

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
