"""Unit tests for evidence parsing, redaction, and report generation."""

from __future__ import annotations

from pathlib import Path

from cloudfirst_aid.evidence import (
    format_evidence_record,
    load_evidence_fixtures,
    redact_sensitive_fields,
    summarize_evidence,
)
from cloudfirst_aid.models import EvidenceItem, Finding, Scenario
from cloudfirst_aid.reports import generate_incident_report, write_incident_report


def test_redact_sensitive_fields() -> None:
    """Verify redaction strips AWS access keys and account IDs."""
    sample = (
        "Found key AKIAIOSFODNN7EXAMPLE and secret wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
        "in account 123456789012."
    )
    redacted = redact_sensitive_fields(sample)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "AKIA****************" in redacted
    assert "123456789012" not in redacted
    assert "************" in redacted


def test_format_evidence_record() -> None:
    """Verify evidence string formatting."""
    item = EvidenceItem(
        id="SIM-001",
        scenario_id="CFA-001",
        description="SSH test",
        source="ssh",
        observation="timed out",
        provenance="simulated",
    )
    formatted = format_evidence_record(item)
    assert "Evidence: SIM-001" in formatted
    assert "Provenance:  simulated" in formatted
    assert "Observation:" in formatted


def test_summarize_evidence_by_provenance() -> None:
    """Verify evidence items are grouped into proper provenance buckets."""
    items = [
        EvidenceItem("1", "CFA-001", "d1", "s", "o", "simulated"),
        EvidenceItem("2", "CFA-001", "d2", "s", "o", "local"),
        EvidenceItem("3", "CFA-001", "d3", "s", "o", "live_aws"),
    ]
    summary = summarize_evidence(items)
    assert len(summary["simulated"]) == 1
    assert len(summary["local"]) == 1
    assert len(summary["live_aws"]) == 1


def test_generate_incident_report(catalog: list[Scenario]) -> None:
    """Verify incident report markdown structure."""
    scenario = catalog[0]
    evidence = load_evidence_fixtures(scenario.id)
    findings = [
        Finding(
            description="Firewall blocking traffic",
            status="confirmed",
            evidence_ids=["SIM-EVID-CFA001-03"],
            explanation="No port 22 ingress rule found",
        )
    ]
    report_md = generate_incident_report(scenario, evidence, findings)

    assert f"# Incident Investigation Report: {scenario.id}" in report_md
    assert "## 1. Incident Overview" in report_md
    assert "## 2. Diagnostic Evidence & Provenance" in report_md
    assert "## 3. Triage & Diagnostic Findings" in report_md
    assert "## 4. Remediation Guidance" in report_md
    assert "## 5. Verification & Prevention" in report_md
    assert "## 6. Official References" in report_md


def test_write_incident_report_to_disk(tmp_path: Path) -> None:
    """Verify report writer creates directories and files cleanly."""
    report_md = "# Sample Test Report"
    out_file = tmp_path / "nested" / "report.md"
    written_path = write_incident_report(report_md, out_file)

    assert written_path.exists()
    assert written_path.read_text(encoding="utf-8") == report_md
