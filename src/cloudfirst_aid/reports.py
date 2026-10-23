"""Incident report generator.

Transforms scenario definitions, collected/simulated evidence items,
and triage findings into a structured Markdown post-mortem incident report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cloudfirst_aid.evidence import redact_sensitive_fields
from cloudfirst_aid.models import EvidenceItem, Finding, Scenario


def generate_incident_report(
    scenario: Scenario,
    evidence: list[EvidenceItem],
    findings: list[Finding],
    operator: str = "CloudFirst Aid Diagnostic Engine",
) -> str:
    """Generate a clean Markdown incident report.

    Distinguishes observed facts, supported findings, and unconfirmed hypotheses.
    Highlights evidence provenance (simulated vs. local vs. live AWS).
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Group evidence provenance
    simulated_count = sum(1 for e in evidence if e.provenance == "simulated")
    local_count = sum(1 for e in evidence if e.provenance == "local")
    live_count = sum(1 for e in evidence if e.provenance == "live_aws")

    lines: list[str] = [
        f"# Incident Investigation Report: {scenario.id}",
        "",
        f"**Title:** {scenario.title}  ",
        f"**Category:** {scenario.category.capitalize()} | **Severity:** {scenario.severity.upper()} | **Difficulty:** {scenario.difficulty.capitalize()}  ",
        f"**Generated:** {now_utc}  ",
        f"**Investigating Agent / Operator:** {operator}  ",
        "",
        "---",
        "",
        "## 1. Incident Overview",
        "",
        f"**Reported Symptom:**  \n> {scenario.symptom}",
        "",
    ]

    if scenario.initial_observations:
        lines.append("**Initial Observations:**")
        for obs in scenario.initial_observations:
            lines.append(f"- {obs}")
        lines.append("")

    if scenario.environment:
        lines.append(f"**Target Environment / Prerequisites:**  \n{scenario.environment}\n")

    lines.extend([
        "## 2. Diagnostic Evidence & Provenance",
        "",
        f"> **Provenance Summary:** {simulated_count} Simulated Fixtures | {local_count} Local System Checks | {live_count} Live AWS Observations",
        "",
    ])

    if not evidence:
        lines.append("_No evidence records were provided for this investigation._\n")
    else:
        for idx, item in enumerate(evidence, 1):
            sanitized_id = redact_sensitive_fields(item.id)
            sanitized_desc = redact_sensitive_fields(item.description)
            sanitized_src = redact_sensitive_fields(item.source)
            sanitized_date = redact_sensitive_fields(item.collected_at) if item.collected_at else "Fixture / Undated"
            sanitized_obs = redact_sensitive_fields(item.observation.strip())

            lines.extend([
                f"### Evidence Item {idx}: `{sanitized_id}` ({item.provenance.upper()})",
                f"- **Description:** {sanitized_desc}",
                f"- **Source Command / API:** `{sanitized_src}`",
                f"- **Recorded At:** {sanitized_date}",
                "",
                "```text",
                sanitized_obs,
                "```",
                "",
            ])
            if item.limitations:
                lines.append(f"> **Known Limitation:** {redact_sensitive_fields(item.limitations)}\n")

    lines.extend([
        "## 3. Triage & Diagnostic Findings",
        "",
        "Evaluation of evidence against deterministic troubleshooting rules:",
        "",
    ])

    if not findings:
        lines.append("_No diagnostic findings derived from the current evidence set._\n")
    else:
        for idx, finding in enumerate(findings, 1):
            badge = finding.status.upper()
            sanitized_desc = redact_sensitive_fields(finding.description)
            lines.extend([
                f"### Finding {idx}: [{badge}] {sanitized_desc}",
                f"- **Status:** `{finding.status}`",
            ])
            if finding.evidence_ids:
                sanitized_eids = [redact_sensitive_fields(eid) for eid in finding.evidence_ids]
                lines.append(f"- **Supporting Evidence:** {', '.join(sanitized_eids)}")
            if finding.explanation:
                lines.append(f"- **Diagnostic Explanation:** {redact_sensitive_fields(finding.explanation)}")
            lines.append("")

    lines.extend([
        "## 4. Remediation Guidance",
        "",
    ])

    if scenario.possible_causes:
        lines.append("Recommended corrective actions based on candidate root causes:")
        lines.append("")
        for cause in scenario.possible_causes:
            lines.extend([
                f"### If Cause is: {cause.cause} (Likelihood: {cause.likelihood})",
                f"**Required Evidence to Confirm:** {cause.evidence_needed}",
                "",
                "**Remediation Steps:**",
                f"{cause.remediation}",
                "",
            ])
    else:
        lines.append("_Refer to the specific scenario runbook for remediation instructions._\n")

    lines.extend([
        "## 5. Verification & Prevention",
        "",
        f"**Verification Procedure:**  \n{scenario.verification or 'Follow runbook verification steps.'}",
        "",
    ])

    if scenario.prevention:
        lines.append("**Prevention & Monitoring Best Practices:**")
        for prev in scenario.prevention:
            lines.append(f"- {prev}")
        lines.append("")

    if scenario.references:
        lines.append("## 6. Official References")
        lines.append("")
        for ref in scenario.references:
            lines.append(f"- [{ref}]({ref})")
        lines.append("")

    lines.extend([
        "---",
        "_Report compiled by CloudFirst Aid — offline-first AWS & Linux support diagnostic lab._",
        "",
    ])

    return "\n".join(lines)


def write_incident_report(report_markdown: str, output_path: Path) -> Path:
    """Save report markdown to file, ensuring parent directories exist."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_markdown, encoding="utf-8")
    return output_path
