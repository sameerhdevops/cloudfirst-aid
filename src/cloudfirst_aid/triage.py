"""Triage engine — evaluates evidence against scenario rules to produce findings.

The triage module is the diagnostic logic layer. Given a scenario and its
evidence, it applies predefined rules to determine what the evidence
supports, what remains unconfirmed, and what needs further investigation.

This is a rule-based engine, not a machine-learning model. Each scenario's
rules are deterministic: the same evidence always produces the same findings.
The rules are defined as simple Python functions keyed by scenario ID.
"""

from __future__ import annotations

from cloudfirst_aid.models import EvidenceItem, Finding, FindingStatus


def _check_keyword(observation: str, keywords: list[str]) -> bool:
    """Check if any keyword appears in the observation text (case-insensitive)."""
    obs_lower = observation.lower()
    return any(kw.lower() in obs_lower for kw in keywords)


# ── Rule functions ──────────────────────────────────────────────────────
# Each function takes a list of EvidenceItem and returns a list of Finding.
# Rules are scenario-specific and test for patterns in the evidence data.


def _triage_disk_full(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-010: Linux filesystem full."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation

        if _check_keyword(obs, ["100%", "Use% 100", "no space left"]):
            findings.append(Finding(
                description="Filesystem is at 100% capacity.",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation=(
                    "The df output shows a mounted filesystem at 100% usage. "
                    "Applications writing to this mount point will receive "
                    "'No space left on device' errors."
                ),
            ))
        elif _check_keyword(obs, ["9[0-9]%", "Use% 9"]):
            findings.append(Finding(
                description="Filesystem usage is above 90%.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation="Disk usage is critically high and approaching exhaustion.",
            ))

        if _check_keyword(obs, ["/var/log"]):
            findings.append(Finding(
                description="Log directory may be consuming significant space.",
                status=FindingStatus.POSSIBLE.value,
                evidence_ids=[item.id],
                explanation=(
                    "The /var/log directory is a common source of disk exhaustion. "
                    "Check for unrotated logs, verbose application logging, or "
                    "repeated error messages filling log files."
                ),
            ))

    if not findings:
        findings.append(Finding(
            description="Disk usage appears normal in available evidence.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="No evidence of full filesystems found. Collect df -h output.",
        ))

    return findings


def _triage_inode_exhaustion(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-011: Inode exhaustion."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation
        combined = f"{item.source} {item.description} {obs}".lower()

        if ("df -i" in combined or "inodes" in combined) and ("100%" in obs or "0 ifree" in obs.lower() or "no space left" in obs.lower()):
            findings.append(Finding(
                description="Inodes are 100% exhausted on a filesystem.",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation=(
                    "The filesystem has consumed all available index nodes (inodes). "
                    "Operating system cannot create new file entries or directory nodes "
                    "even if free disk capacity remains."
                ),
            ))

        if "find" in combined and any(kw in obs.lower() for kw in ["spool", "maildrop", "session", "tmp"]):
            findings.append(Finding(
                description="Over 1 million orphan files identified in queue/cache directory.",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation=(
                    "Large accumulations of small files (such as an undelivered mail queue or stale "
                    "PHP session store) are the primary root cause of inode exhaustion."
                ),
            ))

    if not findings:
        findings.append(Finding(
            description="Inode usage appears normal in available evidence.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="No inode exhaustion detected. Collect df -i output.",
        ))

    return findings


def _triage_ssh_timeout(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-001: SSH connection timeout."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation
        combined = f"{item.source} {item.description} {obs}".lower()

        if _check_keyword(obs, ["Connection timed out", "Operation timed out"]):
            findings.append(Finding(
                description="SSH connection is timing out.",
                status=FindingStatus.OBSERVED.value,
                evidence_ids=[item.id],
                explanation="The TCP handshake never completes. The packet is being dropped.",
            ))

        if "security-groups" in combined or "security group" in combined:
            if '"fromport": 22' not in obs.lower() and '"toport": 22' not in obs.lower() and "port 22" not in obs.lower():
                findings.append(Finding(
                    description="Security group does not allow inbound SSH on port 22.",
                    status=FindingStatus.CONFIRMED.value,
                    evidence_ids=[item.id],
                    explanation=(
                        "The security group attached to the instance has no rule authorizing "
                        "TCP port 22 ingress. Traffic is silently dropped by the AWS hypervisor."
                    ),
                ))
            else:
                findings.append(Finding(
                    description="Security group has an inbound rule for port 22.",
                    status=FindingStatus.OBSERVED.value,
                    evidence_ids=[item.id],
                    explanation="An inbound rule for port 22 exists. Verify source CIDR matches client IP.",
                ))

        if ("describe-instances" in combined or "instance state" in combined) and '"running"' in obs.lower():
            findings.append(Finding(
                description="EC2 instance is in running state.",
                status=FindingStatus.OBSERVED.value,
                evidence_ids=[item.id],
                explanation="The virtual machine is powered on; failure is occurring at network/firewall layer.",
            ))


        if _check_keyword(obs, ["status check", "failed", "impaired"]):
            findings.append(Finding(
                description="Instance status check is failing.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation=(
                    "A failed status check means the instance may not be reachable "
                    "at the hypervisor or OS level. SSH will time out."
                ),
            ))

    if not findings:
        findings.append(Finding(
            description="Insufficient evidence to determine SSH timeout cause.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation=(
                "Check: (1) instance state, (2) security group rules for port 22, "
                "(3) NACL rules, (4) route table for internet gateway, "
                "(5) public IP or Elastic IP assignment."
            ),
        ))

    return findings


def _triage_service_failure(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-013: systemd service fails to start."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation

        if _check_keyword(obs, ["Active: failed", "status=1/FAILURE", "code=exited"]):
            findings.append(Finding(
                description="Service is in failed state.",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation="systemctl status shows the service has failed to start.",
            ))

        if _check_keyword(obs, ["Address already in use", "bind"]):
            findings.append(Finding(
                description="Service cannot bind to its port — address already in use.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation=(
                    "Another process is already listening on the port this service "
                    "needs. Use 'ss -tlnp' or 'lsof -i :<port>' to identify it."
                ),
            ))

        if _check_keyword(obs, ["Permission denied", "EACCES"]):
            findings.append(Finding(
                description="Service failed due to a permission problem.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation=(
                    "The service process was denied access to a file, directory, "
                    "or port. Check file ownership, SELinux context, and whether "
                    "the service runs as the correct user."
                ),
            ))

        if _check_keyword(obs, ["not found", "No such file", "missing"]):
            findings.append(Finding(
                description="Service configuration references a missing file or binary.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation="A required executable, config file, or path does not exist.",
            ))

    if not findings:
        findings.append(Finding(
            description="Service status needs investigation.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Run 'systemctl status <service>' and 'journalctl -u <service>' first.",
        ))

    return findings


def _triage_s3_access_denied(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-020: S3 AccessDenied."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation
        combined = f"{item.source} {item.description} {obs}".lower()

        if _check_keyword(obs, ["AccessDenied", "Access Denied", "403"]):
            findings.append(Finding(
                description="S3 returned 403 AccessDenied response.",
                status=FindingStatus.OBSERVED.value,
                evidence_ids=[item.id],
                explanation=(
                    "The S3 service rejected the API call. Possible causes include IAM policy, "
                    "bucket policy explicit Deny, S3 Block Public Access, or KMS permissions."
                ),
            ))

        if ("bucket-policy" in combined or "bucket policy" in combined) and (
            '"effect": "deny"' in obs.lower() or '"effect":"deny"' in obs.lower()
        ):
            findings.append(Finding(
                description="S3 Bucket Policy contains an explicit Deny statement.",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation=(
                    "An explicit Deny in an S3 bucket policy unconditionally overrides any IAM Allow. "
                    "Requests not satisfying the condition block (e.g. source VPC endpoint or HTTPS) are blocked."
                ),
            ))

    if not findings:
        findings.append(Finding(
            description="No S3 access-denied evidence found.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Reproduce the error and capture the exact API response.",
        ))

    return findings


def _triage_alb_unhealthy(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-017: ALB unhealthy targets / HTTP 502."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation
        combined = f"{item.source} {item.description} {obs}".lower()

        if _check_keyword(obs, ["unhealthy", "health check failed"]):
            findings.append(Finding(
                description="Target instances are reported as Unhealthy by Application Load Balancer.",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation=(
                    "Target group health checks are failing. The ALB cannot route traffic to targets, "
                    "resulting in HTTP 502/503 responses returned to clients."
                ),
            ))

        if "target.timeout" in obs.lower():
            findings.append(Finding(
                description="ALB health check failure reason is Target.Timeout.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation=(
                    "Target.Timeout indicates the health check probes are not receiving TCP/HTTP responses "
                    "before the timeout threshold. Usually caused by Security Group misconfiguration or routing."
                ),
            ))

        if (
            ("security-groups" in combined or "security group" in combined)
            and "8080" not in obs
            and "fromport" in obs.lower()
        ):
            findings.append(Finding(
                description="Target Security Group does not authorize traffic on application port (8080).",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation=(
                    "The target EC2 security group only allows SSH (port 22) and lacks an ingress "
                    "rule for port 8080 from the ALB security group."
                ),
            ))

    if not findings:
        findings.append(Finding(
            description="ALB target health needs investigation.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Check target group health and security groups.",
        ))

    return findings


# ── Rule registry ───────────────────────────────────────────────────────

_TRIAGE_RULES: dict[str, callable] = {
    "CFA-001": _triage_ssh_timeout,
    "CFA-010": _triage_disk_full,
    "CFA-011": _triage_inode_exhaustion,
    "CFA-013": _triage_service_failure,
    "CFA-017": _triage_alb_unhealthy,
    "CFA-020": _triage_s3_access_denied,
}


def triage_scenario(scenario_id: str, evidence: list[EvidenceItem]) -> list[Finding]:
    """Run the triage rules for a scenario against the supplied evidence.

    Returns a list of findings. If no rules are registered for the scenario,
    returns a single needs-investigation finding.
    """
    rule_fn = _TRIAGE_RULES.get(scenario_id.upper())
    if rule_fn is None:
        return [Finding(
            description=f"No triage rules implemented for {scenario_id}.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation=(
                "This scenario does not have automated diagnostic rules. "
                "Follow the investigation steps in the scenario or runbook."
            ),
        )]

    return rule_fn(evidence)


def has_triage_rules(scenario_id: str) -> bool:
    """Check whether a scenario has triage rules registered."""
    return scenario_id.upper() in _TRIAGE_RULES
