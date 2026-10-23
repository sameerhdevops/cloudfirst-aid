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
- **Incident Report Generator:** Markdown report compiler transforming scenarios, evidence items, and triage findings into audit-ready post-mortems.
- **Architecture Diagrams:** Created Mermaid source diagrams and Markdown documentation for Project Architecture, Reference AWS Website Architecture, Incident Investigation Workflow, and Troubleshooting Decision Flow.
- **Testing Suite:** Added 32 automated unit tests covering catalog validation, CLI commands, triage logic, evidence handling, report generation, and mocked read-only AWS inspection.
- **Continuous Integration:** Configured GitHub Actions workflow (`tests.yml`) testing on Python 3.10, 3.11, 3.12, 3.13, and 3.14.
- **Safe Diagnostic Scripts:** Added `collect_linux_diagnostics.sh`, `validate.ps1`, and `validate.sh`.
