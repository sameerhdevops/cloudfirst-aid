"""Data models for scenarios, evidence, and findings.

These are plain dataclasses — no ORM, no framework dependencies.
Each model maps directly to the JSON scenario schema and can be
constructed from a parsed dictionary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    """Operational impact classification."""

    CRITICAL = "critical"    # Service fully down, users affected
    HIGH = "high"            # Major degradation, partial outage
    MEDIUM = "medium"        # Noticeable issue, workaround exists
    LOW = "low"              # Minor issue, no immediate user impact


class Difficulty(Enum):
    """Investigation difficulty for a learner."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class EvidenceProvenance(Enum):
    """Where a piece of evidence came from."""

    SIMULATED = "simulated"      # Fixture data supplied with the project
    LOCAL = "local"              # Collected from the local machine
    LIVE_AWS = "live_aws"        # Collected from a real AWS API call


class FindingStatus(Enum):
    """How confident we are in a diagnostic finding."""

    OBSERVED = "observed"        # A fact we can see in the evidence
    POSSIBLE = "possible"        # A plausible cause, not yet confirmed
    SUPPORTED = "supported"      # Evidence points toward this cause
    CONFIRMED = "confirmed"      # Sufficient evidence to act on this
    NEEDS_INVESTIGATION = "needs_investigation"  # More data required


@dataclass
class InvestigationStep:
    """A single diagnostic check in an investigation sequence."""

    order: int
    title: str
    command: str
    explanation: str
    what_to_look_for: str
    next_if_normal: str = ""
    next_if_abnormal: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InvestigationStep:
        return cls(
            order=data["order"],
            title=data["title"],
            command=data.get("command", ""),
            explanation=data.get("explanation", ""),
            what_to_look_for=data.get("what_to_look_for", ""),
            next_if_normal=data.get("next_if_normal", ""),
            next_if_abnormal=data.get("next_if_abnormal", ""),
        )


@dataclass
class PossibleCause:
    """A cause that may explain the reported symptom."""

    cause: str
    likelihood: str  # "common", "occasional", "rare"
    evidence_needed: str
    remediation: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PossibleCause:
        return cls(
            cause=data["cause"],
            likelihood=data.get("likelihood", "unknown"),
            evidence_needed=data.get("evidence_needed", ""),
            remediation=data.get("remediation", ""),
        )


@dataclass
class Scenario:
    """A single troubleshooting scenario from the catalog."""

    id: str
    title: str
    category: str
    difficulty: str
    severity: str
    symptom: str
    initial_observations: list[str] = field(default_factory=list)
    environment: str = ""
    possible_causes: list[PossibleCause] = field(default_factory=list)
    investigation_steps: list[InvestigationStep] = field(default_factory=list)
    verification: str = ""
    prevention: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    has_runbook: bool = False
    has_demo: bool = False
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scenario:
        """Build a Scenario from a parsed JSON dictionary."""
        causes = [PossibleCause.from_dict(c) for c in data.get("possible_causes", [])]
        steps = [InvestigationStep.from_dict(s) for s in data.get("investigation_steps", [])]
        return cls(
            id=data["id"],
            title=data["title"],
            category=data["category"],
            difficulty=data.get("difficulty", "beginner"),
            severity=data.get("severity", "medium"),
            symptom=data["symptom"],
            initial_observations=data.get("initial_observations", []),
            environment=data.get("environment", ""),
            possible_causes=causes,
            investigation_steps=steps,
            verification=data.get("verification", ""),
            prevention=data.get("prevention", []),
            references=data.get("references", []),
            has_runbook=data.get("has_runbook", False),
            has_demo=data.get("has_demo", False),
            tags=data.get("tags", []),
        )


@dataclass
class EvidenceItem:
    """A single piece of diagnostic evidence."""

    id: str
    scenario_id: str
    description: str
    source: str               # What command or check produced this
    observation: str           # What was actually observed
    provenance: str            # "simulated", "local", or "live_aws"
    collected_at: str = ""     # ISO timestamp, empty if simulated
    limitations: str = ""      # What this evidence does NOT prove

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceItem:
        return cls(
            id=data["id"],
            scenario_id=data["scenario_id"],
            description=data["description"],
            source=data.get("source", ""),
            observation=data.get("observation", ""),
            provenance=data.get("provenance", "simulated"),
            collected_at=data.get("collected_at", ""),
            limitations=data.get("limitations", ""),
        )


@dataclass
class Finding:
    """A diagnostic conclusion drawn from evidence."""

    description: str
    status: str    # Use FindingStatus values
    evidence_ids: list[str] = field(default_factory=list)
    explanation: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        return cls(
            description=data["description"],
            status=data.get("status", "possible"),
            evidence_ids=data.get("evidence_ids", []),
            explanation=data.get("explanation", ""),
        )
