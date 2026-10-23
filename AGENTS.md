# CloudFirst Aid — Developer & Maintainer Guide

This guide provides technical context, development guidelines, coding standards, and verification procedures for developers, maintainers, and agentic coding tools contributing to **CloudFirst Aid**.

---

## 1. Project Principles & Core Invariants

CloudFirst Aid is designed as a practical troubleshooting lab and portfolio project demonstrating entry-level AWS Cloud Support and Linux troubleshooting.

All contributions must uphold four architectural invariants:

1. **Offline-First Execution:** The core functionality (catalog loading, schema validation, evidence triage, Markdown report generation) must execute 100% locally with zero external network dependencies and zero mandatory cloud credentials.
2. **Deterministic Diagnostic Logic:** The triage engine (`triage.py`) consists of deterministic Python functions that map structured evidence observations to findings (`CONFIRMED`, `SUPPORTED`, `POSSIBLE`, `OBSERVED`, `NEEDS_INVESTIGATION`). It does not invoke non-deterministic LLMs at runtime.
3. **Safe & Non-Destructive Operations:** Never provide or recommend shell commands that unconditionally delete directories (`rm -rf /`), format filesystems, or alter cloud infrastructure without explicit pre-checks and impact warnings.
4. **Read-Only Cloud Access:** Any optional live AWS interaction uses strictly read-only APIs (`Describe*`, `Get*`). Automated tests must never incur cloud charges or require live credentials.

---

## 2. Repository Architecture & Layout

```text
cloudfirst-aid/
├── scenarios/
│   ├── catalog/              # 30 individual scenario JSON specifications (CFA-001 through CFA-030)
│   └── schema.json           # JSON Schema definition for scenario files
├── runbooks/                 # 14 comprehensive, step-by-step diagnostic runbooks
│   ├── ec2/
│   ├── linux/
│   ├── networking/
│   └── aws-services/
├── src/cloudfirst_aid/
│   ├── __init__.py           # Package version definition
│   ├── models.py             # Dataclass domain models (Scenario, EvidenceItem, Finding)
│   ├── catalog.py            # Scenario loader and validation engine
│   ├── triage.py             # Rule-based diagnostic evaluation engine
│   ├── evidence.py           # Evidence loader and automated redaction engine
│   ├── reports.py            # Markdown incident report compiler
│   ├── aws_readonly.py       # Optional live AWS inspection module (read-only)
│   ├── cli.py                # Command-line interface entry points
│   └── data/scenarios/       # Bundled package scenario data
├── tests/
│   ├── unit/                 # Pytest unit tests (catalog, CLI, triage, reports, models)
│   ├── integration/          # Multi-step CLI workflow tests
│   └── fixtures/             # Simulated evidence JSON records
├── scripts/                  # Cross-platform validation and smoke test scripts
│   ├── validate.sh           # Bash validation suite
│   ├── validate.ps1          # PowerShell validation suite
│   └── collect_linux_diagnostics.sh # Standalone Linux host diagnostic collector
└── docs/                     # Architectural decision records, diagrams, and guides
```

---

## 3. Contribution Workflows & Standards

### Python & Code Quality Standards
- **Python Support:** Target Python 3.10 through 3.14.
- **Type Annotations:** Full type annotations required (`from __future__ import annotations`).
- **Formatting & Linting:** Codebase is formatted and linted using `ruff`. Run `ruff check src tests` before committing.
- **Tone & Documentation:** Avoid promotional language, corporate jargon, or inflated claims (e.g. avoid "production-grade", "audit-ready", "revolutionary", "seamless"). Use direct, precise engineering prose that explains *what* a command does and *why*.

### Adding or Updating Scenarios
1. Scenarios live in `scenarios/catalog/CFA-xxx_<name>.json` and must conform to `scenarios/schema.json`.
2. Each scenario must provide concrete symptoms, initial observations, a difficulty level (`beginner`, `intermediate`, `advanced`), relevant documentation links, and verification steps.
3. When adding a scenario, update the bundled copy in `src/cloudfirst_aid/data/scenarios/` if packaging data.

### Adding or Updating Triage Rules
1. Implement scenario rules in `src/cloudfirst_aid/triage.py` as dedicated functions `_triage_<name>(evidence: list[EvidenceItem]) -> list[Finding]`.
2. Register the rule in `_TRIAGE_RULES` dictionary with the uppercase scenario ID.
3. Every rule must handle incomplete, malformed, or contradictory evidence gracefully without raising uncaught exceptions, returning `FindingStatus.NEEDS_INVESTIGATION` when evidence is insufficient.
4. Distinguish between:
   - `CONFIRMED`: Direct, indisputable evidence proves the root cause (e.g., `df -h` shows 100% utilization on mount `/`).
   - `SUPPORTED`: Evidence strongly corroborates the condition but requires a secondary confirmation.
   - `POSSIBLE`: Plausible cause suggested by symptoms or directory sizes.
   - `OBSERVED`: Symptom or fact recorded directly from system output (e.g., HTTP 502 returned).
   - `NEEDS_INVESTIGATION`: Missing diagnostic data required to reach a conclusion.

### Writing Runbooks
1. Organize runbooks into standard sections:
   - Problem Statement
   - What the Engineer Sees (actual terminal output and error strings)
   - Before Changing Anything (safe prerequisites, architectural context, blast radius warnings)
   - Investigation Sequence (step-by-step diagnostic sequence)
   - Possible Causes & Likelihood table
   - Remediation (concrete, verified commands)
   - Verification (how to prove the issue is resolved)
   - Prevention & Best Practices
   - Interview Discussion Points (common interview questions and technical answers)
   - Official References
2. **Command Classification:** Clearly classify every command in the investigation and remediation sequences as:
   - `(Read-only Diagnostic)`: Zero impact, safe to run in any state.
   - `(Local System Change)`: Modifies host configuration, services, or packages.
   - `(AWS Infrastructure Change)`: Modifies cloud resources, security groups, or routing tables.

---

## 4. Testing & Verification Gates

Before submitting changes or releasing, all quality gates must pass:

1. **Unit and Integration Tests:**
   ```bash
   pytest tests/unit -v
   ```
2. **Linting:**
   ```bash
   ruff check src tests
   ```
3. **Cross-Platform Validation Script:**
   ```powershell
   # On Windows:
   powershell -ExecutionPolicy Bypass -File scripts\validate.ps1

   # On Linux/macOS:
   bash scripts/validate.sh
   ```
4. **Offline Verification:**
   Ensure tests pass in an environment without internet access or AWS credentials (`AWS_ACCESS_KEY_ID="" AWS_SECRET_ACCESS_KEY=""`).
