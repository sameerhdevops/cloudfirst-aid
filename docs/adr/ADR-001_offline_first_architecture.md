# ADR-001: Offline-First Architecture for Troubleshooting Education

## Status
Accepted

## Date
2026-10-23

## Context
Cloud support engineering candidates (freshers and junior engineers) preparing for technical interviews require practical, realistic experience investigating production incidents across Linux systems and AWS cloud environments. However, cloud infrastructure incurs financial costs, requires live credit cards, and creates credential leakage hazards if beginners make mistakes during local development.

Furthermore, simulating failures by deliberately destroying or misconfiguring real AWS infrastructure or a developer's personal machine is hazardous, non-reproducible, and expensive.

## Decision
CloudFirst Aid adopts an **offline-first, zero-cloud-dependency** architectural core:
1. All 30 troubleshooting scenarios, runbooks, and diagnostic evaluation rules are stored locally in version-controlled JSON and Markdown assets.
2. Incident triage is powered by deterministic rule evaluation operating on supplied diagnostic evidence fixtures (`tests/fixtures/evidence_*.json`) or safe, non-destructive local system snapshots.
3. No AWS credentials, credit card, or active internet connection is required to run the CLI, validate the catalog, execute triage tests, or generate structured incident reports.

## Consequences

### Positive
- **Zero Financial Cost:** Freshers can study and practice indefinitely without worrying about AWS billing or surprise charges.
- **Safety by Default:** No commands can accidentally delete production resources, drop databases, or alter live security groups.
- **100% Deterministic & Reproducible:** Unit tests and CI pipelines run instantly and consistently in any standard Python environment.
- **Interview Focus:** Forces candidates to understand the diagnostic sequence, log patterns, and causality rather than just clicking console buttons.

### Negative / Trade-Offs
- The tool does not automatically fix live cloud resources (remediation instructions remain prescriptive guidance for humans).
- Advanced live AWS API edge cases require manual testing or our optional read-only inspection module.
