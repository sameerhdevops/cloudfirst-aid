# Getting Started with CloudFirst Aid

This guide walks you through setting up CloudFirst Aid locally, exploring the scenario catalog, running deterministic triage demonstrations, and generating incident reports.

---

## Prerequisites

- **Python:** Version 3.10 or newer (tested on Python 3.10, 3.11, 3.12, 3.13, 3.14).
- **Git:** Version 2.25+.
- **Operating System:** Windows (PowerShell), macOS, or Linux / WSL.
- **AWS Credentials:** **NOT REQUIRED** for local operation, catalog exploration, or running tests.

---

## Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/sameerhdevops/cloudfirst-aid.git
cd cloudfirst-aid
```

### 2. Create and Activate a Local Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Linux / macOS (Bash):
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install in Editable Mode with Development Dependencies
```bash
pip install -e ".[dev]"
```

*Note:* If you want optional live AWS read-only inspection support:
```bash
pip install -e ".[dev,aws]"
```

---

## Exploring the CLI

### 1. Check Installation & CLI Version
```bash
cloudfirst-aid --version
# Expected: cloudfirst-aid 0.1.0
```

### 2. List All 30 Troubleshooting Scenarios
```bash
cloudfirst-aid list
```

Filter by specific category:
```bash
cloudfirst-aid list --category linux
cloudfirst-aid list --category ec2
cloudfirst-aid list --category networking
```

### 3. Inspect a Specific Scenario and Investigation Sequence
```bash
cloudfirst-aid show CFA-001
```
Output displays:
- Reported symptom and initial observations.
- Possible root causes and likelihood.
- Step-by-step ordered investigation sequence with exact diagnostic commands and what output to observe.
- Verification and prevention guidance.

### 4. Validate the Scenario Catalog
Ensure all 30 scenario JSON files conform to required schemas without errors or duplicate IDs:
```bash
cloudfirst-aid validate
```
Expected output:
```text
Validating 30 scenario files...
OK: Catalog is structurally valid.
  Total Scenarios: 30
  Categories:      application, ec2, iam-s3, linux, monitoring, networking
  With Demo:       6
  With Runbook:    14
```

---

## Running Triage Demonstrations

CloudFirst Aid includes 6 deterministic evidence fixtures that reproduce real incident conditions. Run the triage engine to evaluate the evidence against diagnostic rules:

```bash
# 1. EC2 SSH Connection Timeout
cloudfirst-aid triage CFA-001

# 2. Linux Root Filesystem 100% Full
cloudfirst-aid triage CFA-010

# 3. Linux Inode Exhaustion (0 Inodes Available)
cloudfirst-aid triage CFA-011

# 4. systemd Service Failure / Address Already in Use
cloudfirst-aid triage CFA-013

# 5. Application Load Balancer Unhealthy Targets
cloudfirst-aid triage CFA-017

# 6. S3 AccessDenied / Bucket Policy Explicit Deny
cloudfirst-aid triage CFA-020
```

---

## Generating Incident Reports

Compile scenario metadata, diagnostic evidence, and triage findings into an audit-ready Markdown post-mortem report:

```bash
# Output report directly to terminal stdout:
cloudfirst-aid report CFA-001

# Save report directly to file:
cloudfirst-aid report CFA-001 --output my_report.md
```

Inspect the generated file in your preferred markdown viewer or text editor.

---

## Running the Automated Test Suite

Run the complete automated unit test suite:
```bash
pytest tests/unit -v
```

Run static linting with Ruff:
```bash
ruff check src tests
```

Execute the local validation script:
- On Windows (PowerShell):
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\validate.ps1
  ```
- On Linux / macOS (Bash):
  ```bash
  bash scripts/validate.sh
  ```
