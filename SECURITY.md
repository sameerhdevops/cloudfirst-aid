# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

---

## Reporting a Vulnerability

Security is a primary design consideration for CloudFirst Aid. Because this tool handles diagnostic evidence and AWS configuration metadata, we take credential hygiene and safe execution seriously.

If you discover a security vulnerability—such as an unhandled credential leak, insecure command recommendation in a runbook, or path traversal risk—please report it responsibly:

- **Reporting Channel:** Please submit a private security advisory through GitHub via [GitHub Security Advisories](https://github.com/sameerhdevops/cloudfirst-aid/security/advisories/new).
- **Do not open public GitHub issues** containing unpatched vulnerabilities or active exploit details.

Reports will be reviewed and addressed as maintainer availability permits. Safe local verification steps and proposed patches are welcomed.

---

## Safety & Security Invariants

CloudFirst Aid adheres to the following non-negotiable safety rules:
1. **Zero Auto-Execution of Destructive Commands:** The application never executes `rm -rf`, disk format commands, partition tables alterations, or OS daemon reconfigurations.
2. **Read-Only Cloud Access:** Any optional live AWS interaction uses strictly read-only APIs (`Describe*`, `Get*`). The codebase contains zero calls to resource creation, deletion, or permission modification APIs.
3. **Automated Secret Redaction:** Evidence ingestion strips AWS Access Key IDs (`AKIA...`), secret credentials, and 12-digit account numbers before displaying or saving reports.
