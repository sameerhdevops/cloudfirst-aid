"""Triage engine — evaluates evidence against scenario rules to produce findings.

The triage module is the diagnostic logic layer. Given a scenario and its
evidence, it applies deterministic rules to determine what the evidence
supports, what remains unconfirmed, and what needs further investigation.

This is a rule-based engine, not a machine-learning model. Each scenario's
rules are deterministic: the same evidence always produces the same findings.
"""

from __future__ import annotations

import json
import re
from typing import Any

from cloudfirst_aid.models import EvidenceItem, Finding, FindingStatus


def _extract_filesystem_usage(text: str) -> list[tuple[int, str]]:
    """Extract (usage_percent, mount_or_device) from df or filesystem status output.

    Avoids matching unrelated percentages (e.g., '95% confidence').
    """
    results: list[tuple[int, str]] = []

    # Match standard df -h lines: /dev/xxx ... 20G 20G 0 100% /
    # or columns ending in % followed by a mount point
    df_pattern = re.compile(
        r"(?:^|\n)\s*(\S+)\s+\S+\s+\S+\s+\S+\s+([0-9]{1,3})%\s+(\S+)",
        re.MULTILINE,
    )
    for match in df_pattern.finditer(text):
        dev, pct_str, mount = match.groups()
        pct = int(pct_str)
        # Verify it looks like a device or filesystem line
        if "/" in dev or "/" in mount or mount == "/":
            results.append((pct, mount))

    # Match explicit "Use% <number>" or "Capacity: <number>%"
    use_pct_pattern = re.compile(
        r"(?:Use%|Capacity|disk\s+usage|filesystem\s+usage)[:\s]+([0-9]{1,3})%",
        re.IGNORECASE,
    )
    for match in use_pct_pattern.finditer(text):
        pct = int(match.group(1))
        results.append((pct, "filesystem"))

    return results


def _triage_disk_full(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-010: Linux filesystem full."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation
        obs_lower = obs.lower()

        # Check for explicit 'no space left on device' OS error
        if "no space left on device" in obs_lower or "cannot create temp file" in obs_lower:
            findings.append(Finding(
                description="Write operations are failing with 'No space left on device'.",
                status=FindingStatus.OBSERVED.value,
                evidence_ids=[item.id],
                explanation=(
                    "The operating system kernel returned ENOSPC to an application "
                    "or shell command attempting to allocate storage blocks."
                ),
            ))

        # Check structured filesystem usage
        fs_usages = _extract_filesystem_usage(obs)
        for pct, mount in fs_usages:
            if pct >= 100:
                findings.append(Finding(
                    description=f"Filesystem at '{mount}' is at 100% block capacity.",
                    status=FindingStatus.CONFIRMED.value,
                    evidence_ids=[item.id],
                    explanation=(
                        f"Command output verifies 0 free storage blocks remaining on '{mount}'. "
                        "New file creation and append operations will fail immediately."
                    ),
                ))
            elif pct >= 90:
                findings.append(Finding(
                    description=f"Filesystem at '{mount}' is critically full ({pct}% utilized).",
                    status=FindingStatus.SUPPORTED.value,
                    evidence_ids=[item.id],
                    explanation=(
                        f"Filesystem utilization on '{mount}' is at {pct}%, which exceeds "
                        "the standard 90% emergency threshold and risks imminent exhaustion."
                    ),
                ))

        # Check for directory space analysis (e.g. du -sh /var/log/*)
        if "/var/log" in obs:
            large_log_match = re.search(r"([0-9]+[MG])\s+/var/log", obs)
            size_info = f" ({large_log_match.group(1)})" if large_log_match else ""
            findings.append(Finding(
                description=f"Log directory /var/log consumes significant storage{size_info}.",
                status=FindingStatus.POSSIBLE.value,
                evidence_ids=[item.id],
                explanation=(
                    "The /var/log directory is identified as a primary contributor to "
                    "disk consumption. Check for unrotated logs or repeated errors."
                ),
            ))

        # Check for specific runaway unrotated log file
        log_file_match = re.search(r"-rw-[\w-]+\s+\d+\s+\S+\s+\S+\s+([0-9]+[MG])\s+.*?(app-[\w.-]+\.log|\w+\.log)", obs)
        if log_file_match:
            size_str, filename = log_file_match.groups()
            findings.append(Finding(
                description=f"Unrotated log file '{filename}' consumes {size_str} of storage.",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation=(
                    f"Directory listing confirms that '{filename}' has grown without "
                    "rotation and accounts for the majority of used disk capacity."
                ),
            ))

        # Check for deleted open files (lsof)
        if "(deleted)" in obs_lower and "lsof" in item.source.lower():
            findings.append(Finding(
                description="Deleted files are still held open by running processes.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation=(
                    "lsof indicates unlinked files retain allocated disk blocks because "
                    "active processes still maintain open file descriptors."
                ),
            ))

    if not findings:
        findings.append(Finding(
            description="Insufficient or inconclusive evidence of disk exhaustion.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Provide 'df -h' and 'du -sh /var/*' output to evaluate storage utilization.",
        ))

    return findings


def _triage_inode_exhaustion(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-011: Inode exhaustion."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation
        obs_lower = obs.lower()
        combined = f"{item.source} {item.description} {obs}".lower()

        # Check df -i table lines
        if "df -i" in combined or "inod" in combined:
            for df_i_match in re.finditer(r"(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9]{1,3})%\s+(\S+)", obs):
                _dev, _total, _used, free, pct_str, mount = df_i_match.groups()
                pct = int(pct_str)
                if pct >= 100 or int(free) == 0:
                    findings.append(Finding(
                        description=f"Inodes are 100% exhausted on filesystem '{mount}'.",
                        status=FindingStatus.CONFIRMED.value,
                        evidence_ids=[item.id],
                        explanation=(
                            f"Output demonstrates 0 available index nodes on '{mount}'. "
                            "Even if free disk block space remains, no new files, directories, "
                            "or sockets can be created."
                        ),
                    ))
                elif pct >= 90:
                    findings.append(Finding(
                        description=f"Inode utilization is critically high ({pct}%) on '{mount}'.",
                        status=FindingStatus.SUPPORTED.value,
                        evidence_ids=[item.id],
                        explanation=f"Filesystem '{mount}' has consumed {pct}% of total index nodes.",
                    ))

        # Check concrete file counts from find / wc output
        count_match = re.search(r"^\s*([0-9]{4,10})\s+([/\w.-]+)", obs, re.MULTILINE)
        if count_match:
            count = int(count_match.group(1))
            directory = count_match.group(2)
            if count >= 100000:
                findings.append(Finding(
                    description=f"Heavy accumulation of small files ({count:,} entries) in '{directory}'.",
                    status=FindingStatus.CONFIRMED.value,
                    evidence_ids=[item.id],
                    explanation=(
                        f"Directory file count query confirms {count:,} individual files in '{directory}', "
                        "accounting for the severe index node consumption."
                    ),
                ))
            else:
                findings.append(Finding(
                    description=f"Found {count:,} files in '{directory}'.",
                    status=FindingStatus.OBSERVED.value,
                    evidence_ids=[item.id],
                    explanation=f"Directory '{directory}' contains {count:,} file entries.",
                ))
        elif "find" in combined and any(kw in obs_lower for kw in ["spool", "maildrop", "session", "tmp"]):
            # Directory mentioned without concrete count
            findings.append(Finding(
                description="Queue or cache directory identified as candidate accumulation site.",
                status=FindingStatus.POSSIBLE.value,
                evidence_ids=[item.id],
                explanation=(
                    "Temporary and queue directories frequently experience small-file accumulation, "
                    "but specific file count data is required to confirm."
                ),
            ))

    if not findings:
        findings.append(Finding(
            description="Insufficient evidence to evaluate inode exhaustion.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Provide 'df -i' output and file count inspections to confirm inode status.",
        ))

    return findings


def _triage_ssh_timeout(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-001: SSH connection timeout."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation
        obs_lower = obs.lower()
        combined = f"{item.source} {item.description} {obs}".lower()

        # 1. Observed timeout
        if "connection timed out" in obs_lower or "operation timed out" in obs_lower:
            findings.append(Finding(
                description="SSH client connection timed out.",
                status=FindingStatus.OBSERVED.value,
                evidence_ids=[item.id],
                explanation=(
                    "The TCP three-way handshake never completed. Inbound or outbound "
                    "packets are being dropped along the network path."
                ),
            ))

        # 2. Host / Instance State
        if "describe-instances" in combined or "instance state" in combined:
            if '"running"' in obs_lower or "'running'" in obs_lower:
                findings.append(Finding(
                    description="EC2 instance is in running state.",
                    status=FindingStatus.OBSERVED.value,
                    evidence_ids=[item.id],
                    explanation=(
                        "The virtual machine is powered on and hypervisor status is active; "
                        "the timeout is originating at the network or host firewall layer."
                    ),
                ))
            elif '"stopped"' in obs_lower:
                findings.append(Finding(
                    description="EC2 instance is stopped.",
                    status=FindingStatus.CONFIRMED.value,
                    evidence_ids=[item.id],
                    explanation="The target instance is powered off; network connectivity is impossible.",
                ))

        # 3. Security Group Analysis
        if "describe-security-groups" in combined or "security group" in combined:
            # Attempt to parse rules JSON
            parsed_rules: list[dict[str, Any]] | None = None
            try:
                data = json.loads(obs)
                if isinstance(data, list):
                    parsed_rules = data
                elif isinstance(data, dict) and "SecurityGroups" in data:
                    parsed_rules = data["SecurityGroups"][0].get("IpPermissions", [])
                elif isinstance(data, dict) and "IpPermissions" in data:
                    parsed_rules = data.get("IpPermissions", [])
            except Exception:
                parsed_rules = None

            if parsed_rules is not None:
                # Complete parsed ruleset available
                port_22_rules = [
                    r for r in parsed_rules
                    if (r.get("FromPort") == 22 or r.get("ToPort") == 22 or r.get("IpProtocol") == "-1")
                ]
                if not port_22_rules:
                    findings.append(Finding(
                        description="Security group does not allow inbound SSH on port 22.",
                        status=FindingStatus.CONFIRMED.value,
                        evidence_ids=[item.id],
                        explanation=(
                            "The attached security group ingress ruleset was inspected and "
                            "contains no rule authorizing TCP port 22. Inbound packets are dropped."
                        ),
                    ))
                else:
                    findings.append(Finding(
                        description="Security group contains an inbound rule authorizing port 22.",
                        status=FindingStatus.OBSERVED.value,
                        evidence_ids=[item.id],
                        explanation=(
                            "Port 22 ingress is permitted in the security group. Verify that the "
                            "client's current public IP matches the allowed source CIDR ranges."
                        ),
                    ))
            elif "22" in obs and ("fromport" in obs_lower or "port 22" in obs_lower):
                findings.append(Finding(
                    description="Security group appears to have a port 22 rule.",
                    status=FindingStatus.SUPPORTED.value,
                    evidence_ids=[item.id],
                    explanation="Evidence text references port 22 in security group configuration.",
                ))
            elif obs.strip().startswith("[") and obs.strip().endswith("]"):
                # Empty rules list: []
                findings.append(Finding(
                    description="Security group has zero inbound ingress rules.",
                    status=FindingStatus.CONFIRMED.value,
                    evidence_ids=[item.id],
                    explanation="The ingress ruleset is empty; all inbound traffic is dropped by default.",
                ))
            else:
                findings.append(Finding(
                    description="Security group evidence is incomplete or inconclusive.",
                    status=FindingStatus.NEEDS_INVESTIGATION.value,
                    evidence_ids=[item.id],
                    explanation="Could not verify full security group ingress rules from provided observation.",
                ))

        # 4. Status Checks
        if ("describe-instance-status" in combined or "status check" in combined) and (
            "impaired" in obs_lower or "failed" in obs_lower
        ):
            findings.append(Finding(
                description="EC2 status check is impaired.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation="An impaired system or instance status check can cause network unreachability.",
            ))

    if not findings:
        findings.append(Finding(
            description="Insufficient evidence to evaluate SSH timeout.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Collect SSH client verbose trace (-v) and 'aws ec2 describe-security-groups' output.",
        ))

    return findings


def _triage_service_failure(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-013: systemd service fails to start."""
    findings: list[Finding] = []

    for item in evidence:
        obs = item.observation
        obs_lower = obs.lower()

        # 1. Active status check
        if "active: failed" in obs_lower or "status=1/failure" in obs_lower or "code=exited" in obs_lower:
            findings.append(Finding(
                description="Service process is in failed state.",
                status=FindingStatus.CONFIRMED.value,
                evidence_ids=[item.id],
                explanation="systemctl status indicates the service process exited unsuccessfully.",
            ))

        # 2. Specific Port Conflict (require address already in use, not loose 'bind')
        if "address already in use" in obs_lower or "eaddrinuse" in obs_lower:
            # Check if conflicting process is identified
            ss_match = re.search(r'users:\(\("([^"]+)",pid=(\d+)', obs)
            if ss_match:
                proc_name, pid = ss_match.groups()
                findings.append(Finding(
                    description=f"Port collision: PID {pid} ('{proc_name}') already occupies listening port.",
                    status=FindingStatus.CONFIRMED.value,
                    evidence_ids=[item.id],
                    explanation=(
                        f"Socket inspection reveals that process '{proc_name}' (PID {pid}) "
                        "is already bound to the required port, preventing the service from starting."
                    ),
                ))
            else:
                findings.append(Finding(
                    description="Service failed to bind socket: Address already in use.",
                    status=FindingStatus.CONFIRMED.value,
                    evidence_ids=[item.id],
                    explanation="Process startup log records 'bind: Address already in use'.",
                ))

        # 3. Executable binary missing (exit code 127)
        if "status=127" in obs_lower or "failed at step exec" in obs_lower or "no such file or directory" in obs_lower:
            findings.append(Finding(
                description="Service binary or ExecStart path not found (exit status 127).",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation=(
                    "systemd failed to execute the binary specified in ExecStart directive. "
                    "Verify file existence and absolute binary path."
                ),
            ))

        # 4. Permission errors
        if "permission denied" in obs_lower or "eacces" in obs_lower or "status=203/exec" in obs_lower:
            findings.append(Finding(
                description="Service startup failed due to file or port permission restrictions.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation=(
                    "Process was denied access to a configured socket, directory, or executable. "
                    "Inspect service User/Group directive and file ownership."
                ),
            ))

        # 5. Configuration syntax error
        if "syntax error" in obs_lower or "configuration error" in obs_lower or "failed to parse" in obs_lower:
            findings.append(Finding(
                description="Configuration file parsing or syntax error.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id],
                explanation="Service startup failed while reading its configuration file.",
            ))

    if not findings:
        findings.append(Finding(
            description="Service status requires investigation.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Provide 'systemctl status <service>' and 'journalctl -u <service>' output.",
        ))

    return findings


def _triage_alb_unhealthy(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-017: ALB unhealthy targets / HTTP 502.

    Performs two-phase diagnostic evaluation to ensure strict order independence:
    1. Extracts target ports, ALB SG identifiers, and target health reason codes from all evidence.
    2. Evaluates target security group rules against the verified target ports and load balancer origin.
    """
    findings: list[Finding] = []

    target_ports: set[int] = set()
    has_unhealthy_targets = False
    has_healthy_targets = False
    alb_sg_ids: set[str] = set()
    sg_evidence_items: list[EvidenceItem] = []
    health_evidence_items: list[EvidenceItem] = []
    observed_502 = False
    reason_timeout = False
    reason_mismatch = None
    reason_refused = False

    # Phase 1: Context extraction across all evidence items
    for item in evidence:
        obs = item.observation
        obs_lower = obs.lower()
        combined = f"{item.source} {item.description} {obs}".lower()

        # Track target health
        if "targethealthdescriptions" in obs_lower or "targethealth" in obs_lower:
            health_evidence_items.append(item)
            if "unhealthy" in obs_lower or "failed" in obs_lower:
                has_unhealthy_targets = True
            elif "healthy" in obs_lower:
                has_healthy_targets = True

            # Extract target port dynamically from TargetHealthDescriptions
            for pm in re.findall(r'"Port":\s*(\d+)', obs):
                target_ports.add(int(pm))

            # Reason codes
            if "target.timeout" in obs_lower:
                reason_timeout = True
            if "target.responsecodemismatch" in obs_lower:
                code_match = re.search(r"codes:\s*\[(\d+)\]", obs)
                reason_mismatch = f"HTTP {code_match.group(1)}" if code_match else "unexpected HTTP code"
            if "target.failedconnection" in obs_lower or "connection refused" in obs_lower:
                reason_refused = True

        # Track ALB SG from describe-load-balancers or references
        if "describe-load-balancers" in combined or "loadbalancer" in combined or "alb" in combined:
            for sg_match in re.findall(r"\b(sg-[0-9a-fA-F]+)\b", obs):
                if "target" not in sg_match.lower():
                    alb_sg_ids.add(sg_match.lower())

        # Track Security Group evidence
        if (
            "describe-security-groups" in combined
            or "describe-security-group" in combined
            or "security group" in combined
            or "security-group" in combined
            or "securitygrouprules" in obs_lower
        ):
            sg_evidence_items.append(item)

        # Track 502/503 HTTP errors
        if "502" in obs and ("bad gateway" in obs_lower or "http/1.1 502" in obs_lower):
            observed_502 = True

    # Phase 2: Formulate findings
    if observed_502:
        findings.append(Finding(
            description="Load balancer returned HTTP 502 Bad Gateway to clients.",
            status=FindingStatus.OBSERVED.value,
            evidence_ids=[item.id for item in evidence if "502" in item.observation and "bad gateway" in item.observation.lower()],
            explanation="The load balancer returned 502 because all registered targets were unavailable or uncontactable.",
        ))

    if has_unhealthy_targets:
        findings.append(Finding(
            description="Application Load Balancer target group reports targets as Unhealthy.",
            status=FindingStatus.CONFIRMED.value,
            evidence_ids=[item.id for item in health_evidence_items],
            explanation=(
                "Target group health checks are failing. The load balancer cannot route "
                "client traffic to unhealthy backend instances."
            ),
        ))

        if reason_timeout:
            findings.append(Finding(
                description="Health check probe failed with reason: Target.Timeout.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id for item in health_evidence_items],
                explanation=(
                    "Target.Timeout indicates the health check probe received no response before "
                    "the configured timeout. Common causes include Security Group drops or routing."
                ),
            ))
        if reason_mismatch:
            findings.append(Finding(
                description=f"Health check probe failed with reason: Target.ResponseCodeMismatch ({reason_mismatch}).",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id for item in health_evidence_items],
                explanation=(
                    f"Target returned {reason_mismatch}, which does not match the configured "
                    "target group HTTP status matcher (default 200)."
                ),
            ))
        if reason_refused:
            findings.append(Finding(
                description="Health check probe failed with reason: Target.FailedConnection.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id for item in health_evidence_items],
                explanation="Connection to target was refused; the backend process is not listening on that port.",
            ))
    elif has_healthy_targets:
        findings.append(Finding(
            description="Registered targets are reporting Healthy state.",
            status=FindingStatus.OBSERVED.value,
            evidence_ids=[item.id for item in health_evidence_items],
            explanation="Target group health checks are succeeding for all registered instances.",
        ))

    # Evaluate Security Group rules against target ports
    if sg_evidence_items:
        if not target_ports:
            findings.append(Finding(
                description="Target application port is unknown from available evidence; cannot verify Security Group ingress rules.",
                status=FindingStatus.NEEDS_INVESTIGATION.value,
                evidence_ids=[item.id for item in sg_evidence_items],
                explanation=(
                    "Security group rules were provided, but the target group port was not found in evidence. "
                    "Collect 'aws elbv2 describe-target-health' to establish the target port."
                ),
            ))
        else:
            for p in sorted(target_ports):
                port_authorized = False
                has_any_port_rule = False

                for item in sg_evidence_items:
                    obs = item.observation
                    obs_lower = obs.lower()

                    port_rule_regex = rf'"FromPort":\s*{p}\b|\bport\s+{p}\b'
                    if re.search(port_rule_regex, obs, re.IGNORECASE) or f'"fromport": {p}' in obs_lower:
                        has_any_port_rule = True

                        if alb_sg_ids:
                            for alb_sg in alb_sg_ids:
                                if alb_sg in obs_lower:
                                    port_authorized = True
                                    break
                        elif (
                            '"cidr_ip": "0.0.0.0/0"' in obs_lower
                            or '"cidrip": "0.0.0.0/0"' in obs_lower
                            or "0.0.0.0/0" in obs
                            or "useridgrouppairs" in obs_lower
                            or "groupid" in obs_lower
                        ):
                            port_authorized = True

                if not has_any_port_rule:
                    findings.append(Finding(
                        description=f"Target Security Group does not authorize traffic on target port {p}.",
                        status=FindingStatus.CONFIRMED.value,
                        evidence_ids=[item.id for item in sg_evidence_items],
                        explanation=(
                            f"Attached target security group has no ingress rule for port {p}. "
                            "Health check probes from the ALB are dropped."
                        ),
                    ))
                elif not port_authorized and alb_sg_ids:
                    findings.append(Finding(
                        description=f"Target Security Group contains an ingress rule for port {p}, but source group does not match Load Balancer SG.",
                        status=FindingStatus.CONFIRMED.value,
                        evidence_ids=[item.id for item in sg_evidence_items],
                        explanation=(
                            f"Ingress rule exists for port {p}, but does not permit traffic from ALB security group "
                            f"{', '.join(alb_sg_ids)}."
                        ),
                    ))
                else:
                    findings.append(Finding(
                        description=f"Target Security Group contains an ingress rule for port {p}.",
                        status=FindingStatus.OBSERVED.value,
                        evidence_ids=[item.id for item in sg_evidence_items],
                        explanation=f"Ingress rule for port {p} exists in target security group.",
                    ))

    if not findings:
        findings.append(Finding(
            description="ALB target health requires investigation.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Collect 'aws elbv2 describe-target-health' and security group rules.",
        ))

    return findings


def _triage_s3_access_denied(evidence: list[EvidenceItem]) -> list[Finding]:
    """CFA-020: S3 AccessDenied / Bucket Policy triage."""
    findings: list[Finding] = []

    access_denied_items: list[EvidenceItem] = []
    bucket_policy_items: list[EvidenceItem] = []
    caller_context_items: list[EvidenceItem] = []
    iam_items: list[EvidenceItem] = []
    kms_items: list[EvidenceItem] = []

    caller_vpce: str | None = None
    caller_is_external: bool = False
    caller_is_https: bool | None = None

    # Step 1: Analyze evidence items across all sources
    for item in evidence:
        obs = item.observation
        obs_lower = obs.lower()
        src_lower = item.source.lower()
        desc_lower = item.description.lower()
        combined = f"{src_lower} {desc_lower} {obs_lower}"

        if "accessdenied" in obs_lower or "access denied" in obs_lower:
            access_denied_items.append(item)

        if "bucket-policy" in combined or "bucket policy" in combined or "get-bucket-policy" in src_lower:
            bucket_policy_items.append(item)

        # Detect caller network / transport context
        if (
            "workstation" in combined
            or "direct internet" in combined
            or "public ip" in combined
            or "no attached vpc endpoint" in combined
            or "external" in combined
        ):
            caller_context_items.append(item)
            caller_is_external = True
            if "no attached vpc endpoint" in combined:
                caller_vpce = ""

        # Check for caller VPC endpoint in non-bucket-policy evidence
        if "bucket-policy" not in combined and "get-bucket-policy" not in src_lower:
            vpce_match = re.search(r"\b(vpce-[0-9a-zA-Z]+)\b", obs, re.IGNORECASE)
            if vpce_match:
                caller_vpce = vpce_match.group(1).lower()
                caller_context_items.append(item)

        # Check for transport scheme
        if "http://" in src_lower or "transport: http" in combined:
            caller_is_https = False
            caller_context_items.append(item)
        elif "https://" in src_lower or "transport: https" in combined or "ssl: true" in combined:
            caller_is_https = True
            caller_context_items.append(item)

        if "no identity-based policy" in obs_lower or "not authorized to perform" in obs_lower:
            iam_items.append(item)

        if "kms" in obs_lower and ("kms:decrypt" in obs_lower or "kms exception" in obs_lower):
            kms_items.append(item)

    # Step 2: Record AccessDenied observation if observed
    if access_denied_items:
        findings.append(Finding(
            description="Amazon S3 API returned 403 AccessDenied response.",
            status=FindingStatus.OBSERVED.value,
            evidence_ids=[item.id for item in access_denied_items],
            explanation=(
                "The S3 service rejected the request with 403 AccessDenied. Possible causes include "
                "an explicit Deny in bucket policy or SCP, missing IAM permissions, S3 Block Public Access, "
                "or KMS key policy restrictions."
            ),
        ))

    # Step 3: Parse and evaluate Bucket Policy statements
    for bp_item in bucket_policy_items:
        policy_dict = None
        obs = bp_item.observation.strip()
        try:
            json_start = obs.find("{")
            json_end = obs.rfind("}")
            if json_start != -1 and json_end != -1 and json_end > json_start:
                policy_dict = json.loads(obs[json_start:json_end + 1])
        except Exception:
            policy_dict = None

        if policy_dict and isinstance(policy_dict, dict) and "Statement" in policy_dict:
            raw_stmts = policy_dict["Statement"]
            statements = raw_stmts if isinstance(raw_stmts, list) else [raw_stmts]
            deny_stmts = [s for s in statements if isinstance(s, dict) and s.get("Effect") == "Deny"]

            if not deny_stmts:
                findings.append(Finding(
                    description="Bucket policy contains no explicit Deny statements.",
                    status=FindingStatus.OBSERVED.value,
                    evidence_ids=[bp_item.id],
                    explanation=(
                        "The inspected bucket policy contains no explicit Deny statements. The 403 AccessDenied "
                        "is likely caused by missing IAM permissions, KMS key permissions, or an SCP."
                    ),
                ))
            else:
                for stmt in deny_stmts:
                    sid = stmt.get("Sid", "ExplicitDeny")
                    cond = stmt.get("Condition", {})
                    has_vpce = False
                    vpce_expected: str | None = None
                    vpce_op: str | None = None

                    if isinstance(cond, dict):
                        for op_name, op_rules in cond.items():
                            if isinstance(op_rules, dict):
                                for cond_key, cond_val in op_rules.items():
                                    if cond_key.lower() == "aws:sourcevpce":
                                        has_vpce = True
                                        vpce_expected = str(cond_val)
                                        vpce_op = op_name
                                    elif cond_key.lower() == "aws:securetransport":
                                        is_deny_unencrypted = str(cond_val).lower() == "false"
                                        if is_deny_unencrypted:
                                            if caller_is_https is False:
                                                findings.append(Finding(
                                                    description=f"Bucket policy statement '{sid}' explicitly denies unencrypted HTTP requests.",
                                                    status=FindingStatus.CONFIRMED.value,
                                                    evidence_ids=[bp_item.id] + [c.id for c in caller_context_items],
                                                    explanation="Caller made an unencrypted HTTP request, triggering aws:SecureTransport: false Deny.",
                                                ))
                                            elif caller_is_https is True:
                                                findings.append(Finding(
                                                    description=f"Bucket policy statement '{sid}' enforces TLS, but caller is using HTTPS.",
                                                    status=FindingStatus.OBSERVED.value,
                                                    evidence_ids=[bp_item.id],
                                                    explanation="The SecureTransport condition is satisfied by caller HTTPS transport.",
                                                ))
                                            else:
                                                findings.append(Finding(
                                                    description=f"Bucket policy statement '{sid}' explicitly denies unencrypted HTTP traffic.",
                                                    status=FindingStatus.SUPPORTED.value,
                                                    evidence_ids=[bp_item.id],
                                                    explanation="Bucket policy requires TLS (aws:SecureTransport: false). Verify whether caller used HTTP.",
                                                ))

                    if has_vpce and vpce_expected:
                        is_not_equals = "not" in vpce_op.lower() if vpce_op else False
                        if is_not_equals:
                            if caller_is_external or (caller_vpce is not None and caller_vpce.lower() != vpce_expected.lower()):
                                findings.append(Finding(
                                    description=(
                                        f"Bucket policy statement '{sid}' contains an explicit Deny for requests not originating "
                                        f"from VPC endpoint '{vpce_expected}'."
                                    ),
                                    status=FindingStatus.CONFIRMED.value,
                                    evidence_ids=[bp_item.id] + [c.id for c in caller_context_items],
                                    explanation=(
                                        f"The bucket policy enforces an explicit Deny with StringNotEquals for "
                                        f"'{vpce_expected}'. Caller evidence confirms the request originated from "
                                        f"{'an external network with no VPC endpoint' if caller_is_external else f'endpoint {caller_vpce}'}."
                                    ),
                                ))
                            elif caller_vpce is not None and caller_vpce.lower() == vpce_expected.lower():
                                findings.append(Finding(
                                    description=f"Bucket policy statement '{sid}' restricts access to VPC endpoint '{vpce_expected}'.",
                                    status=FindingStatus.OBSERVED.value,
                                    evidence_ids=[bp_item.id] + [c.id for c in caller_context_items],
                                    explanation="Caller matches the required VPC endpoint; this statement does not trigger Deny.",
                                ))
                            else:
                                findings.append(Finding(
                                    description=f"Bucket policy statement '{sid}' restricts access to VPC endpoint '{vpce_expected}'.",
                                    status=FindingStatus.SUPPORTED.value,
                                    evidence_ids=[bp_item.id],
                                    explanation=(
                                        f"The bucket policy contains an explicit Deny for requests not from '{vpce_expected}'. "
                                        f"Caller network origin is not verified in available evidence; confirm caller's VPC endpoint."
                                    ),
                                ))
                        else:
                            # StringEquals
                            if caller_vpce is not None and caller_vpce.lower() == vpce_expected.lower():
                                findings.append(Finding(
                                    description=f"Bucket policy statement '{sid}' contains an explicit Deny for VPC endpoint '{vpce_expected}'.",
                                    status=FindingStatus.CONFIRMED.value,
                                    evidence_ids=[bp_item.id] + [c.id for c in caller_context_items],
                                    explanation=f"Caller request originated from '{vpce_expected}', matching the explicit Deny rule.",
                                ))
                            elif caller_vpce is not None:
                                findings.append(Finding(
                                    description=f"Bucket policy statement '{sid}' denies VPC endpoint '{vpce_expected}'.",
                                    status=FindingStatus.OBSERVED.value,
                                    evidence_ids=[bp_item.id],
                                    explanation="Caller does not match the denied VPC endpoint.",
                                ))
                            else:
                                findings.append(Finding(
                                    description=f"Bucket policy statement '{sid}' explicitly denies VPC endpoint '{vpce_expected}'.",
                                    status=FindingStatus.SUPPORTED.value,
                                    evidence_ids=[bp_item.id],
                                    explanation="Bucket policy denies requests matching this endpoint; caller endpoint unverified in evidence.",
                                ))
                    elif not cond:
                        findings.append(Finding(
                            description=f"Bucket policy statement '{sid}' contains an unconditional explicit Deny.",
                            status=FindingStatus.CONFIRMED.value,
                            evidence_ids=[bp_item.id],
                            explanation="The statement unconditionally denies access to the targeted resource.",
                        ))
        else:
            # Fallback if policy is not valid JSON
            obs_lower = obs.lower()
            if '"effect": "deny"' in obs_lower or '"effect":"deny"' in obs_lower:
                if "aws:sourcevpce" in obs_lower:
                    vpce_match = re.search(r'"aws:sourcevpce":\s*"([^"]+)"', obs, re.IGNORECASE)
                    vpce_id = vpce_match.group(1) if vpce_match else "specified VPC endpoint"
                    if caller_is_external:
                        findings.append(Finding(
                            description=f"Bucket policy contains an explicit Deny for requests not originating from VPC endpoint '{vpce_id}'.",
                            status=FindingStatus.CONFIRMED.value,
                            evidence_ids=[bp_item.id] + [c.id for c in caller_context_items],
                            explanation=f"Caller originated externally without VPC endpoint '{vpce_id}'.",
                        ))
                    else:
                        findings.append(Finding(
                            description=f"Bucket policy contains an explicit Deny for requests not originating from VPC endpoint '{vpce_id}'.",
                            status=FindingStatus.SUPPORTED.value,
                            evidence_ids=[bp_item.id],
                            explanation="Caller network context is unverified in evidence.",
                        ))
                else:
                    findings.append(Finding(
                        description="Bucket policy contains an explicit Deny statement.",
                        status=FindingStatus.SUPPORTED.value,
                        evidence_ids=[bp_item.id],
                        explanation="Explicit Deny present in bucket policy. Verify action, resource, and conditions.",
                    ))

    # Step 4: IAM Permissions findings
    for item in iam_items:
        findings.append(Finding(
            description="Caller identity lacks required IAM permissions.",
            status=FindingStatus.SUPPORTED.value,
            evidence_ids=[item.id],
            explanation="The requesting IAM user or role does not have an identity policy permitting this action.",
        ))

    # Step 5: KMS findings
    for item in kms_items:
        findings.append(Finding(
            description="KMS key policy does not authorize kms:Decrypt for this principal.",
            status=FindingStatus.SUPPORTED.value,
            evidence_ids=[item.id],
            explanation="The S3 object is encrypted with SSE-KMS, but the caller lacks KMS decryption rights.",
        ))

    if not findings:
        findings.append(Finding(
            description="Insufficient evidence to evaluate S3 access denial.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Capture exact S3 API command output and 'aws s3api get-bucket-policy'.",
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
