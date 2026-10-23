# Project Boundaries, Safety, and Limitations

CloudFirst Aid is designed with transparent technical boundaries. It is vital for freshers and candidates presenting this project in technical interviews to speak accurately and honestly about what the project does—and does not—do.

---

## What CloudFirst Aid IS

1. **A Structured Troubleshooting Laboratory:** Provides 30 production-realistic incident scenarios across AWS and Linux environments with ordered diagnostic steps and root-cause analyses.
2. **An Offline-First Diagnostic Engine:** A Python command-line utility that evaluates diagnostic evidence against deterministic troubleshooting rules to derive findings and generate audit reports.
3. **A Field-Grade Runbook Collection:** 14 detailed, original troubleshooting runbooks explaining *why* checks are performed, *what* command outputs indicate, and *how* to remediate failures safely.
4. **An Architectural Demonstration:** Proves clean code organization, test-driven validation, deterministic CI, and safe evidence handling.

---

## What CloudFirst Aid IS NOT

1. **Not a Live Infrastructure Deployment:** CloudFirst Aid does **not** deploy live VPCs, EC2 clusters, or RDS instances. The architecture diagrams represent real-world reference architectures for troubleshooting analysis; they are not active cloud resources.
2. **Not a Claim of Production Experience:** The author does not claim to have managed thousands of production enterprise servers merely because this learning laboratory exists. Rather, it demonstrates that the author has researched and understood real troubleshooting workflows and operational best practices.
3. **Not an Automated Auto-Remediation Tool:** The software does not execute live `aws ec2 authorize-security-group-ingress` or `systemctl restart` commands automatically. In support engineering, human judgment is essential before executing remediations; our tool provides verified recommendations for engineers to apply responsibly.
4. **Not an AI-Generated Hallucination Engine:** CloudFirst Aid does not call external LLMs at runtime to guess answers. Its triage logic is deterministic Python code that evaluates structured evidence against verified operational rules.

---

## Technical Limitations

1. **Deterministic Rule Scope:** Automated triage rules are implemented for the 6 core demonstration scenarios (`CFA-001`, `CFA-010`, `CFA-011`, `CFA-013`, `CFA-017`, `CFA-020`). For the remaining catalog scenarios, the CLI guides the engineer through the documented investigation steps in the scenario JSON and runbooks.
2. **Read-Only AWS Inspector:** The optional `inspect-ec2` command requires an active AWS CLI configuration and `boto3`. It only inspects EC2 instance state and attached security groups; it does not evaluate VPC Flow Logs, NACLs, or Route 53 records in real time.
3. **Windows vs. Linux Script Compatibility:** `scripts/collect_linux_diagnostics.sh` requires a Bash environment (Linux server, Ubuntu WSL, or macOS). On Windows workstations, validation is handled via `scripts/validate.ps1` and Python unit tests.
