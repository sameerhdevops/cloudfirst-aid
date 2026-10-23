# Multi-Agent Architecture & Collaborative Roles

This document outlines how Antigravity's multi-agent capabilities were orchestrated to research, design, test, and verify **CloudFirst Aid**.

---

## Agent Responsibilities & Delegation Model

To ensure high technical precision and prevent cognitive bias or self-review blind spots, work was partitioned across distinct agent roles:

```
                      +-----------------------------+
                      |   Lead Release Coordinator  |
                      |   (Architecture & Synthesis)|
                      +--------------+--------------+
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v                           v                           v
+------------------+        +------------------+        +------------------+
| Technical        |        | QA & Security    |        | Documentation &  |
| Researcher Agent |        | Auditor Agent    |        | Usability Agent  |
| (Official AWS/   |        | (Test Coverage,  |        | (Candidate/      |
| Linux Docs)      |        | Secrets, Safety) |        | Recruiter UX)    |
+------------------+        +------------------+        +------------------+
```

### 1. Lead Release Coordinator (Synthesis & Core Implementation)
- **Scope:** Workspace establishment, package structure, CLI commands (`cli.py`), triage evaluation engine (`triage.py`), catalog schema, and Git publishing.
- **Responsibility:** Holds single-writer ownership of the codebase to prevent file collision, integrates independent research, and executes validation quality gates.

### 2. Technical Researcher Agent
- **Scope:** Primary documentation discovery across official AWS User Guides and upstream Linux manual pages (`man df`, `man ss`, `man systemctl`).
- **Deliverables:** Verified documentation URLs (avoiding hallucinated links), diagnostic sequence definitions, distinguishing characteristics separating similar failure modes (e.g., System vs. Instance status check; 502 vs. 504 status codes).

### 3. QA & Security Auditor Agent
- **Scope:** Independent review of proposed diagnostic advice and automated test coverage.
- **Auditing Invariants:**
  - Verify that no live credentials, access keys (`AKIA...`), or sensitive account ARNs exist in repository files.
  - Verify that tests run 100% offline without requiring AWS credentials or network calls.
  - Audit diagnostic commands for safety (rejecting destructive commands like `rm -rf`, disk reformats, or automatic resource deletion).

### 4. Documentation & Usability Reviewer Agent
- **Scope:** Review runbooks, README, diagrams, and example reports from the perspective of an engineering hiring manager and entry-level fresher.
- **Writing Standards Enforced:**
  - Strip marketing buzzwords ("cutting-edge", "revolutionary", "seamless").
  - Maintain technical precision and transparently document limitations.
  - Ensure setup instructions work cleanly from a fresh clone without unstated dependencies.

---

## Single-Writer Principle
To maintain codebase integrity:
- Multiple agents never edit the same files concurrently.
- Research and review tasks are assigned in parallel; findings are synthesized by the implementation owner.
- Every check must be physically executed in the terminal environment rather than assumed to pass.
