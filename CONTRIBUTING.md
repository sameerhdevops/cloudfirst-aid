# Contributing to CloudFirst Aid

Thank you for your interest in improving CloudFirst Aid! This project is an open learning resource designed to help engineers prepare for entry-level AWS Cloud Support and Linux systems operations roles.

---

## Ground Rules

1. **Offline-First & Safe by Default:** No contribution may introduce mandatory AWS credentials or paid cloud resource requirements for normal local operation.
2. **Deterministic & Reproducible:** Any new triage rules or scenario demonstrations must be deterministic and covered by automated tests.
3. **No Credential Exposure:** Never submit real AWS access keys, secret tokens, private keys, or confidential hostnames in issues, pull requests, or evidence fixtures.
4. **Natural, Technical Tone:** Keep runbooks direct, technical, and actionable. Avoid marketing hype or generic text.

---

## Development Workflow

1. Fork and clone the repository.
2. Set up your virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Or .\.venv\Scripts\Activate.ps1 on Windows
   pip install -e ".[dev]"
   ```
3. Run the validation checks locally:
   ```bash
   # Run tests
   pytest tests/unit -v

   # Run linter
   ruff check src tests

   # Validate scenario catalog
   cloudfirst-aid validate
   ```
4. Create a focused branch and commit with a clear, descriptive commit message.
5. Open a Pull Request detailing the problem category, scenario additions, or runbook refinements.
