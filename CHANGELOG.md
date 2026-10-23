# Changelog

All notable changes to **CloudFirst Aid** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-10-23

### Added
- **Core CLI Engine:** Implemented `cloudfirst-aid` CLI with subcommands: `list`, `show`, `validate`, `triage`, `report`, and `inspect-ec2`.
- **Scenario Catalog:** Created 30 structured, verified troubleshooting scenarios across 6 categories (`ec2`, `linux`, `networking`, `application`, `iam-s3`, `monitoring`).
- **Field Runbooks:** Authored 14 detailed, original troubleshooting runbooks covering problem analysis, diagnostic commands, root-cause differentiation, remediation, verification, prevention, and interview discussion questions.
- **Deterministic Triage Engine:** Implemented rule-based diagnostic evaluation for 6 core demonstration scenarios (`CFA-001`, `CFA-010`, `CFA-011`, `CFA-013`, `CFA-017`, `CFA-020`).
- **Evidence Handling & Sanitization:** Built automated redaction of AWS access keys (`AKIA...`), secret tokens, and 12-digit account numbers.
- **Incident Report Generator:** Markdown report compiler transforming scenarios, evidence items, and triage findings into structured post-mortem incident reports.
- **Architecture Diagrams:** Created Mermaid source diagrams and Markdown documentation for Project Architecture, Reference AWS Website Architecture, Incident Investigation Workflow, and Troubleshooting Decision Flow.
- **Testing Suite:** Added 46 automated unit tests covering catalog validation, CLI commands, triage logic, evidence handling, report generation, and mocked read-only AWS inspection.
- **Continuous Integration:** Configured GitHub Actions workflow (`tests.yml`) testing on Python 3.10, 3.11, 3.12, 3.13, and 3.14.
- **Safe Diagnostic Scripts:** Added `collect_linux_diagnostics.sh`, `validate.ps1`, and `validate.sh`.

### Changed
- **Evidence Redaction:** Enforced pattern-based secret redaction across all presentation boundaries (`format_evidence_record`, `reports.py`, `cli.py`, `aws_readonly.py`), sanitizing session tokens (`ASIA...`), Bearer headers, and PEM blocks while safely preserving 40-character Git commit hashes.
- **S3 Triage Logic:** Added JSON policy parsing, `aws:sourceVpce` condition operator validation (`StringEquals` vs `StringNotEquals`), `aws:SecureTransport` TLS evaluation, and caller network origin verification.
- **ALB Triage Logic:** Eliminated static fallback ports, added dynamic target port extraction, and implemented two-phase order-independent rule evaluation.
- **Inode Exhaustion Runbook:** Reworked `runbooks/linux/CFA-011_linux_inode_exhaustion.md` to an 8-step cautious investigation sequence with safe preview commands and operational risk analysis.
- **Packaging:** Verified package data distribution ensuring all 30 scenario definitions load cleanly in installed environments outside source checkout.
