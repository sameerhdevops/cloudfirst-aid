# ADR-002: Read-Only Treatment of Live AWS API Inspection

## Status
Accepted

## Date
2026-10-23

## Context
While CloudFirst Aid is strictly offline-first by default, engineers with sandbox AWS accounts may occasionally want to pull live diagnostic evidence (such as an EC2 instance's current state and attached security group rules) to evaluate against the triage engine.

Unrestricted cloud integration introduces severe risks: accidental resource creation/deletion, IAM permission elevation, and accidental credential leakage in terminal logs.

## Decision
Any live AWS integration must adhere to strict safety invariants:
1. **Boto3 is completely optional:** The package works without boto3 installed.
2. **Read-Only APIs exclusively:** Only `Describe*` and `Get*` APIs are allowed. The application will NEVER invoke `Create*`, `Delete*`, `Modify*`, `Authorize*`, or `Revoke*` APIs.
3. **Explicit user opt-in:** Live AWS queries are never executed automatically during normal CLI usage, testing, or startup. They require explicit subcommand invocation (`cloudfirst-aid inspect-ec2 <ID>`).
4. **Automatic Redaction:** Evidence collected via live APIs passes through sanitization logic that redacts AWS Access Key IDs, secret tokens, and 12-digit account numbers before presentation.

## Consequences

### Positive
- Prevents accidental cloud bills and accidental destructive modifications.
- Protects confidential account details from leaking into generated reports or public repositories.
- Keeps CI/CD pipelines independent of cloud credentials.

### Negative / Trade-Offs
- Remediation steps cannot be automated via "one-click fix" CLI flags; the engineer must manually execute verified AWS commands.
