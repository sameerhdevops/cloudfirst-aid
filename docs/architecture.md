# CloudFirst Aid Architecture Guide

CloudFirst Aid is an offline-first troubleshooting laboratory and diagnostic evaluation engine designed for engineers preparing for AWS Cloud Support, Linux Systems Administration, and junior Cloud Operations roles.

---

## 1. Core Architectural Components

```
                           +---------------------------+
                           |   CLI Entrypoint          |
                           |   (src/cloudfirst_aid/    |
                           |    cli.py)                |
                           +-------------+-------------+
                                         |
         +-------------------------------+-------------------------------+
         |                               |                               |
         v                               v                               v
+------------------+           +------------------+           +------------------+
|  Catalog Loader  |           |  Triage Engine   |           | Report Generator |
|  (catalog.py)    |           |  (triage.py)     |           | (reports.py)     |
+--------+---------+           +--------+---------+           +--------+---------+
         |                              |                              |
         v                              v                              v
[scenarios/catalog/*.json]     [tests/fixtures/*.json]        [examples/reports/*.md]
 30 Structured Scenarios        Simulated Evidence             Audit-Ready Reports
```

### Component Responsibilities:
1. **Catalog Subsystem (`models.py`, `catalog.py`):**
   - Loads and parses JSON scenario definitions.
   - Enforces strict structural schema: required fields, unique `CFA-NNN` identifiers, valid category names, and ordered investigation steps.
   - Decoupled from any framework or database; operates directly against plain files.
2. **Evidence Subsystem (`evidence.py`):**
   - Manages diagnostic inputs across three explicit provenance categories: `simulated`, `local`, and `live_aws`.
   - Built-in sanitization engine redacts sensitive strings (AWS access keys, secret tokens, 12-digit account numbers).
3. **Deterministic Triage Engine (`triage.py`):**
   - Applies rule-based diagnostic algorithms to evidence records.
   - Distinguishes five levels of certainty:
     - `observed`: A factual symptom or metric visible in evidence (e.g. "TCP connection is timing out").
     - `possible`: A candidate hypothesis not yet corroborated (e.g. "/var/log may be full").
     - `supported`: Evidence strongly indicates this root cause (e.g. "ALB health check failure reason is Target.Timeout").
     - `confirmed`: Sufficient evidence establishes the exact failure cause (e.g. "Filesystem is at 100% capacity", "Security group does not allow port 22").
     - `needs_investigation`: Insufficient evidence to reach a conclusion.
4. **Report Generator (`reports.py`):**
   - Formats scenarios, evidence records, and triage findings into standardized, audit-ready Markdown incident reports suitable for post-mortems and technical reviews.
5. **Optional Read-Only AWS Inspector (`aws_readonly.py`):**
   - Provides safe, opt-in inspection of live EC2 instance metadata and attached security groups via read-only APIs (`Describe*`).
   - Zero side-effects; never creates, alters, or destroys cloud resources.

---

## 2. Data Flow from Symptom to Incident Report

1. **Intake:** The engineer selects a scenario ID (e.g., `CFA-001`) or specifies a symptom category (`ec2`, `linux`, `networking`, `iam-s3`, `monitoring`, `application`).
2. **Catalog Load:** `catalog.py` loads the corresponding scenario definition, providing the baseline symptom, initial observations, possible root causes, and ordered investigation steps.
3. **Evidence Ingestion:** `evidence.py` loads diagnostic evidence fixtures (`tests/fixtures/evidence_CFA-001.json`), local diagnostic scripts, or optional live AWS metadata.
4. **Triage Evaluation:** `triage.py` passes the evidence through deterministic rules, matching observed patterns to candidate root causes and assigning confidence status (`CONFIRMED`, `SUPPORTED`, `OBSERVED`).
5. **Report Formulation:** `reports.py` merges the scenario definition, raw evidence items (sanitized), and derived findings into an audit report.

---

## 3. Evidence Provenance & Safety Model

CloudFirst Aid strictly separates and labels all diagnostic data:
- **`simulated`**: Fixture data shipped with the repository reproducing known failure conditions (e.g., sample `df -h` or AWS CLI JSON output).
- **`local`**: Data collected safely from the engineer's active operating system (e.g., via `scripts/collect_linux_diagnostics.sh`).
- **`live_aws`**: Data pulled via read-only AWS APIs during explicit user inspection.

Every report includes a Provenance Summary badge so reviewers can distinguish simulated learning scenarios from genuine operational data.

---

## 4. Boundaries and Limitations
- CloudFirst Aid does **not** execute automated fixes against live servers. All remediation is documented as actionable, human-executable commands.
- Triage rules are deterministic and rule-based, not AI-hallucinated. If an evidence fixture lacks necessary data, the engine outputs `needs_investigation` rather than guessing.
