"""Triage engine — evaluates evidence against scenario rules to produce findings.

The triage module is the diagnostic logic layer. Given a scenario and its
evidence, it applies deterministic rules to determine what the evidence
supports, what remains unconfirmed, and what needs further investigation.

This is a rule-based engine, not a machine-learning model. Each scenario's
rules are deterministic: the same evidence always produces the same findings.
"""

from __future__ import annotations

import fnmatch
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


def _extract_json_payload(text: str) -> Any | None:
    """Extract the first complete JSON object or array from command output."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, (dict, list)):
            return payload
    return None


def _policy_values(value: Any) -> list[str]:
    """Normalize policy values that may be strings or arrays."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(entry, str) for entry in value):
        return value
    return []


def _matches_policy_value(actual: str, patterns: list[str], *, case_sensitive: bool = True) -> bool:
    """Match IAM-style wildcard values without treating arbitrary text as a match."""
    if not case_sensitive:
        actual = actual.lower()
        patterns = [pattern.lower() for pattern in patterns]
    return any(fnmatch.fnmatchcase(actual, pattern) for pattern in patterns)


def _extract_s3_request_context(evidence: list[EvidenceItem]) -> dict[str, Any]:
    """Collect only request details supported by non-policy evidence."""
    context: dict[str, Any] = {
        "action": None,
        "resource": None,
        "principal": None,
        "source_vpce": None,
        "external": False,
        "secure_transport": None,
        "context_evidence_ids": [],
    }

    for item in evidence:
        source = item.source or ""
        description = item.description or ""
        observation = item.observation or ""
        combined = f"{source} {description} {observation}"
        combined_lower = combined.lower()
        is_policy = (
            "get-bucket-policy" in source.lower()
            or "bucket-policy" in source.lower()
            or "bucket policy" in description.lower()
        )
        if is_policy:
            continue

        context["context_evidence_ids"].append(item.id)

        if re.search(r"\bgetobject\b|calling the get-object operation", combined_lower):
            context["action"] = "s3:GetObject"
        elif re.search(r"\bputobject\b|calling the put-object operation", combined_lower):
            context["action"] = "s3:PutObject"
        elif re.search(r"\bdeleteobject\b|calling the delete-object operation", combined_lower):
            context["action"] = "s3:DeleteObject"
        elif re.search(r"\blistobjects(?:v2)?\b", combined_lower):
            context["action"] = "s3:ListBucket"

        s3_uri = re.search(r"s3://([^/\s?#]+)(?:/([^\s?#]+))?", combined, re.IGNORECASE)
        virtual_host_url = re.search(
            r"https?://([a-z0-9.-]+)\.s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com(?:/([^\s?#]*))?",
            combined,
            re.IGNORECASE,
        )
        if s3_uri:
            bucket, key = s3_uri.groups()
            context["resource"] = f"arn:aws:s3:::{bucket}" + (f"/{key}" if key else "")
            if key and not context["action"] and "aws s3 cp" in source.lower():
                context["action"] = "s3:GetObject"
        elif virtual_host_url:
            bucket, key = virtual_host_url.groups()
            context["resource"] = f"arn:aws:s3:::{bucket}" + (f"/{key}" if key else "")
            if key and not context["action"] and source.lower().startswith(("curl ", "wget ")):
                context["action"] = "s3:GetObject"

        principal_match = re.search(
            r"\barn:aws(?:-[a-z]+)?:iam::\d{12}:(?:user|role|assumed-role)/[^\s,\"']+",
            combined,
            re.IGNORECASE,
        )
        if principal_match:
            context["principal"] = principal_match.group(0)

        # Only use endpoint IDs from evidence describing the caller, not policy text
        # or a limitations note that merely repeats the endpoint required by a policy.
        if re.search(r"\bcaller\b.*\b(?:through|via|from|using|originat\w*)\b", observation, re.IGNORECASE):
            vpce_match = re.search(r"\bvpce-[0-9a-z]+\b", observation, re.IGNORECASE)
            if vpce_match:
                context["source_vpce"] = vpce_match.group(0).lower()

        if any(
            phrase in observation.lower()
            for phrase in (
                "external developer workstation",
                "direct internet routing",
                "no attached vpc endpoint",
                "external network",
            )
        ):
            context["external"] = True
            if "no attached vpc endpoint" in observation.lower():
                context["source_vpce"] = ""

        transport_text = f"{source} {observation}".lower()
        if "http://" in transport_text or "transport: http" in transport_text:
            context["secure_transport"] = False
        elif "https://" in transport_text or "transport: https" in transport_text:
            context["secure_transport"] = True

    return context


def _principal_matches(statement: dict[str, Any], context: dict[str, Any]) -> bool | None:
    """Check the supported Principal and NotPrincipal forms."""
    principal = context.get("principal")
    if "Principal" in statement:
        value = statement["Principal"]
        if value == "*":
            return True
        if isinstance(value, dict):
            patterns = _policy_values(value.get("AWS"))
            if "*" in patterns:
                return True
            if principal is None or not patterns:
                return None
            return _matches_policy_value(principal, patterns)
        if isinstance(value, str):
            if value == "*":
                return True
            if principal is None:
                return None
            return _matches_policy_value(principal, [value])

    if "NotPrincipal" in statement:
        value = statement["NotPrincipal"]
        if value == "*":
            return False
        patterns: list[str] = []
        if isinstance(value, str):
            patterns = [value]
        elif isinstance(value, dict):
            patterns = _policy_values(value.get("AWS"))
        if principal is None or not patterns:
            return None
        return not _matches_policy_value(principal, patterns)

    return None


def _evaluate_s3_deny_statement(
    statement: dict[str, Any], context: dict[str, Any]
) -> tuple[bool | None, str]:
    """Evaluate a limited subset of bucket-policy applicability.

    This is not a complete IAM policy evaluator. Unsupported condition keys or
    operators produce an inconclusive result rather than a confirmed diagnosis.
    """
    action = context.get("action")
    if "Action" in statement:
        patterns = _policy_values(statement["Action"])
        if action is None or not patterns:
            return None, "The request action is not established by the evidence."
        action_match = _matches_policy_value(action, patterns, case_sensitive=False)
    elif "NotAction" in statement:
        patterns = _policy_values(statement["NotAction"])
        if action is None or not patterns:
            return None, "The request action is not established for the NotAction statement."
        action_match = not _matches_policy_value(action, patterns, case_sensitive=False)
    else:
        return None, "The statement does not provide a supported Action or NotAction field."

    if not action_match:
        return False, "The Deny statement does not cover the observed S3 action."

    resource = context.get("resource")
    if "Resource" in statement:
        patterns = _policy_values(statement["Resource"])
        if resource is None or not patterns:
            return None, "The request resource is not established by the evidence."
        resource_match = _matches_policy_value(resource, patterns)
    elif "NotResource" in statement:
        patterns = _policy_values(statement["NotResource"])
        if resource is None or not patterns:
            return None, "The request resource is not established for the NotResource statement."
        resource_match = not _matches_policy_value(resource, patterns)
    else:
        return None, "The statement does not provide a supported Resource or NotResource field."

    if not resource_match:
        return False, "The Deny statement does not cover the observed S3 resource."

    principal_match = _principal_matches(statement, context)
    if principal_match is False:
        return False, "The statement's Principal does not match the available caller identity."
    if principal_match is None:
        return None, "The caller identity cannot be matched to this statement's Principal."

    condition = statement.get("Condition", {})
    if not condition:
        return True, "The available action, resource, and principal evidence matches an unconditional Deny."

    if not isinstance(condition, dict):
        return None, "The statement's Condition field is not a supported policy object."

    unknown_condition = False
    for operator, operands in condition.items():
        if not isinstance(operands, dict):
            return None, f"Unsupported condition structure for operator {operator}."
        op_lower = operator.lower()

        for key, expected_raw in operands.items():
            key_lower = key.lower()
            expected_values = [str(value).lower() for value in _policy_values(expected_raw)]
            if not expected_values:
                return None, f"Unsupported condition value for {key}."

            if key_lower == "aws:sourcevpce":
                actual = context.get("source_vpce")
                if actual is None:
                    unknown_condition = True
                    continue
                if op_lower == "stringequals":
                    matched = actual.lower() in expected_values
                elif op_lower == "stringnotequals":
                    matched = actual.lower() not in expected_values
                else:
                    return None, f"Unsupported operator {operator} for aws:SourceVpce."
                if not matched:
                    return False, "The aws:SourceVpce condition does not match the observed caller context."

            elif key_lower == "aws:securetransport":
                actual_secure = context.get("secure_transport")
                if actual_secure is None:
                    unknown_condition = True
                    continue
                if op_lower != "bool":
                    return None, f"Unsupported operator {operator} for aws:SecureTransport."
                expected_bools = {value in {"true", "1"} for value in expected_values}
                if actual_secure not in expected_bools:
                    return False, "The aws:SecureTransport condition does not match the observed transport."

            else:
                return None, f"Condition key {key} is outside the supported evaluator scope."

    if unknown_condition:
        return None, "One or more condition values cannot be established from the available request evidence."
    return True, "The supported condition values match the observed request context."


def _parse_security_group_snapshot(
    item: EvidenceItem,
) -> tuple[bool, set[str], list[dict[str, Any]]]:
    """Parse supported AWS security-group response shapes.

    Arbitrary or partial text must not be used to confirm that a rule is absent.
    """
    payload = _extract_json_payload(item.observation or "")
    if payload is None:
        return False, set(), []

    # A paginated AWS response is only a partial snapshot until every page is collected.
    # Never infer that a rule is absent while NextToken indicates more results exist.
    if isinstance(payload, dict) and payload.get("NextToken"):
        return False, set(), []

    groups: set[str] = set()
    rules: list[dict[str, Any]] = []

    if isinstance(payload, dict) and isinstance(payload.get("SecurityGroups"), list):
        payload = payload["SecurityGroups"]
    if isinstance(payload, dict) and "SecurityGroupRules" in payload:
        payload = payload["SecurityGroupRules"]
    if isinstance(payload, dict):
        payload = [payload]

    if not isinstance(payload, list) or not payload or not all(isinstance(row, dict) for row in payload):
        return False, set(), []

    # describe-security-groups response: each group has an IpPermissions list.
    if all("GroupId" in row and isinstance(row.get("IpPermissions"), list) for row in payload):
        for group in payload:
            group_id = str(group["GroupId"]).lower()
            groups.add(group_id)
            for permission in group["IpPermissions"]:
                if not isinstance(permission, dict) or "IpProtocol" not in permission:
                    return False, groups, rules
                source_groups = {
                    str(pair["GroupId"]).lower()
                    for pair in permission.get("UserIdGroupPairs", [])
                    if isinstance(pair, dict) and pair.get("GroupId")
                }
                if permission.get("ReferencedGroupId"):
                    source_groups.add(str(permission["ReferencedGroupId"]).lower())
                cidrs: list[str] = []
                for key in ("IpRanges", "Ipv6Ranges", "PrefixListIds"):
                    for source in permission.get(key, []):
                        if isinstance(source, dict):
                            cidr = source.get("CidrIp") or source.get("CidrIpv6") or source.get("PrefixListId")
                            if cidr:
                                cidrs.append(str(cidr))
                if not source_groups and not cidrs:
                    return False, groups, rules
                protocol = str(permission["IpProtocol"])
                if protocol == "-1":
                    from_port, to_port = 0, 65535
                else:
                    try:
                        from_port = int(permission["FromPort"])
                        to_port = int(permission["ToPort"])
                    except (KeyError, TypeError, ValueError):
                        return False, groups, rules
                rules.append({
                    "group_id": group_id,
                    "from_port": from_port,
                    "to_port": to_port,
                    "protocol": protocol,
                    "source_groups": source_groups,
                    "cidrs": cidrs,
                })
        return True, groups, rules

    # describe-security-group-rules response: IsEgress and target GroupId are needed.
    if all("GroupId" in row and "IsEgress" in row and "IpProtocol" in row for row in payload):
        for row in payload:
            group_id = str(row["GroupId"]).lower()
            groups.add(group_id)
            if row.get("IsEgress") is True:
                continue
            source_groups: set[str] = set()
            if row.get("ReferencedGroupId"):
                source_groups.add(str(row["ReferencedGroupId"]).lower())
            info = row.get("ReferencedGroupInfo")
            if isinstance(info, dict) and info.get("GroupId"):
                source_groups.add(str(info["GroupId"]).lower())
            cidrs = [
                str(row[key]) for key in ("CidrIpv4", "CidrIpv6", "PrefixListId") if row.get(key)
            ]
            if not source_groups and not cidrs:
                return False, groups, rules
            protocol = str(row["IpProtocol"])
            if protocol == "-1":
                from_port, to_port = 0, 65535
            else:
                try:
                    from_port = int(row["FromPort"])
                    to_port = int(row["ToPort"])
                except (KeyError, TypeError, ValueError):
                    return False, groups, rules
            rules.append({
                "group_id": group_id,
                "from_port": from_port,
                "to_port": to_port,
                "protocol": protocol,
                "source_groups": source_groups,
                "cidrs": cidrs,
            })
        return True, groups, rules

    return False, groups, rules


def _triage_alb_unhealthy(evidence: list[EvidenceItem]) -> list[Finding]:
    """Evaluate ALB target health and security-group evidence conservatively."""
    findings: list[Finding] = []
    target_ports: set[int] = set()
    health_items: list[EvidenceItem] = []
    security_group_items: list[EvidenceItem] = []
    alb_security_groups: set[str] = set()
    has_unhealthy_targets = False
    has_healthy_targets = False
    reason_timeout = False
    reason_refused = False
    reason_mismatch: str | None = None
    observed_502_items: list[EvidenceItem] = []

    # Collect context first so results do not depend on evidence order.
    for item in evidence:
        source_lower = (item.source or "").lower()
        description_lower = (item.description or "").lower()
        observation = item.observation or ""
        obs_lower = observation.lower()
        combined_lower = f"{source_lower} {description_lower} {obs_lower}"

        if "describe-load-balancers" in source_lower:
            for group_id in re.findall(r"\bsg-[0-9a-f]+\b", observation, re.IGNORECASE):
                alb_security_groups.add(group_id.lower())

        if "describe-target-health" in source_lower or "targethealthdescriptions" in obs_lower:
            health_items.append(item)
            target_ports.update(
                int(port_text)
                for port_text in re.findall(r'"Port"\s*:\s*(\d+)', observation, re.IGNORECASE)
            )
            if (
                re.search(r'"State"\s*:\s*"unhealthy"', obs_lower)
                or "target.timeout" in obs_lower
                or "target.responsecodemismatch" in obs_lower
                or "target.failedconnection" in obs_lower
            ):
                has_unhealthy_targets = True
            if re.search(r'"State"\s*:\s*"healthy"', obs_lower):
                has_healthy_targets = True
            reason_timeout = reason_timeout or "target.timeout" in obs_lower
            reason_refused = reason_refused or "target.failedconnection" in obs_lower or "connection refused" in obs_lower
            if "target.responsecodemismatch" in obs_lower:
                code_match = re.search(r"codes:\s*\[(\d+)\]", observation, re.IGNORECASE)
                reason_mismatch = f"HTTP {code_match.group(1)}" if code_match else "unexpected HTTP code"

        if (
            "describe-security-groups" in source_lower
            or "describe-security-group-rules" in source_lower
            or "security-group-rules" in combined_lower
        ):
            security_group_items.append(item)

        if "502" in observation and ("bad gateway" in obs_lower or "http/1.1 502" in obs_lower):
            observed_502_items.append(item)

    if observed_502_items:
        findings.append(Finding(
            description="Load balancer returned HTTP 502 Bad Gateway to clients.",
            status=FindingStatus.OBSERVED.value,
            evidence_ids=[item.id for item in observed_502_items],
            explanation=(
                "The load balancer returned HTTP 502. The response alone does not establish "
                "whether the cause is target availability, connection handling, or an invalid response."
            ),
        ))

    if has_unhealthy_targets:
        findings.append(Finding(
            description="Application Load Balancer target group reports targets as Unhealthy.",
            status=FindingStatus.CONFIRMED.value,
            evidence_ids=[item.id for item in health_items],
            explanation="The supplied target-health output reports failed health checks; it does not by itself prove the underlying cause.",
        ))
        if reason_timeout:
            findings.append(Finding(
                description="Health check probe failed with reason: Target.Timeout.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id for item in health_items],
                explanation="The probe timed out. Check the target service, port, security groups, routing, and configured timeout.",
            ))
        if reason_mismatch:
            findings.append(Finding(
                description=f"Health check probe failed with reason: Target.ResponseCodeMismatch ({reason_mismatch}).",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id for item in health_items],
                explanation=f"The target returned {reason_mismatch}; compare it with the target group's configured health-check matcher.",
            ))
        if reason_refused:
            findings.append(Finding(
                description="Health check probe failed with reason: Target.FailedConnection.",
                status=FindingStatus.SUPPORTED.value,
                evidence_ids=[item.id for item in health_items],
                explanation="The connection attempt was refused. Check the listening process, bind address, and target port.",
            ))
    elif has_healthy_targets:
        findings.append(Finding(
            description="Target-health evidence reports Healthy targets.",
            status=FindingStatus.OBSERVED.value,
            evidence_ids=[item.id for item in health_items],
            explanation="The supplied health-check output reports healthy targets; it does not prove every application path is working.",
        ))

    if security_group_items:
        snapshots = [_parse_security_group_snapshot(item) for item in security_group_items]
        snapshot_complete = all(complete for complete, _, _ in snapshots)
        target_group_ids = set().union(*(groups for _, groups, _ in snapshots))
        all_rules = [rule for _, _, rules in snapshots for rule in rules]

        if not target_ports:
            findings.append(Finding(
                description="Target application port is unknown; Security Group ingress cannot be evaluated.",
                status=FindingStatus.NEEDS_INVESTIGATION.value,
                evidence_ids=[item.id for item in security_group_items],
                explanation="Collect structured describe-target-health output to establish the target port.",
            ))
        elif not snapshot_complete or not target_group_ids:
            findings.append(Finding(
                description="Security Group evidence is incomplete; ingress findings cannot be confirmed.",
                status=FindingStatus.NEEDS_INVESTIGATION.value,
                evidence_ids=[item.id for item in security_group_items],
                explanation="Provide a complete structured Security Group response, including target GroupId and ingress rules.",
            ))
        else:
            for port in sorted(target_ports):
                target_rules = [
                    rule for rule in all_rules
                    if rule["group_id"] in target_group_ids
                    and rule["protocol"] in {"-1", "tcp"}
                    and rule["from_port"] <= port <= rule["to_port"]
                ]
                if not target_rules:
                    findings.append(Finding(
                        description=f"Target Security Group has no observed ingress rule covering target port {port}.",
                        status=FindingStatus.CONFIRMED.value,
                        evidence_ids=[item.id for item in security_group_items],
                        explanation=(
                            f"The supplied complete ingress snapshot for the identified target group(s) "
                            f"contains no TCP or all-protocol ingress rule covering port {port}."
                        ),
                    ))
                    continue

                if not alb_security_groups:
                    findings.append(Finding(
                        description=f"An ingress rule covers target port {port}, but the ALB source Security Group is unknown.",
                        status=FindingStatus.NEEDS_INVESTIGATION.value,
                        evidence_ids=[item.id for item in security_group_items],
                        explanation="Collect describe-load-balancers output to identify the ALB Security Group before confirming source authorization.",
                    ))
                    continue

                group_authorized = any(
                    rule["source_groups"].intersection(alb_security_groups)
                    for rule in target_rules
                )
                cidr_source_present = any(rule["cidrs"] for rule in target_rules)
                if group_authorized:
                    findings.append(Finding(
                        description=f"Target Security Group has an ingress rule covering port {port} from the ALB Security Group.",
                        status=FindingStatus.OBSERVED.value,
                        evidence_ids=[item.id for item in security_group_items],
                        explanation="The supplied rule references the identified ALB Security Group. Verify the relevant target and rule are the ones in use.",
                    ))
                elif cidr_source_present:
                    findings.append(Finding(
                        description=f"An ingress rule covers target port {port}, but its CIDR source has not been checked against the ALB subnets.",
                        status=FindingStatus.NEEDS_INVESTIGATION.value,
                        evidence_ids=[item.id for item in security_group_items],
                        explanation="CIDR-based access requires subnet/address context; its presence alone does not establish reachability from the ALB.",
                    ))
                else:
                    findings.append(Finding(
                        description=f"Target Security Group rules covering port {port} do not reference the identified ALB Security Group.",
                        status=FindingStatus.CONFIRMED.value,
                        evidence_ids=[item.id for item in security_group_items],
                        explanation="The supplied complete ingress rules for this port reference other Security Groups, not the identified ALB Security Group.",
                    ))

    if not findings:
        findings.append(Finding(
            description="ALB target health requires further investigation.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Collect structured target-health, load-balancer, and target Security Group output.",
        ))
    return findings


def _triage_s3_access_denied(evidence: list[EvidenceItem]) -> list[Finding]:
    """Evaluate S3 AccessDenied evidence against a limited, explicit policy subset."""
    findings: list[Finding] = []
    access_denied_items: list[EvidenceItem] = []
    bucket_policy_items: list[EvidenceItem] = []
    iam_items: list[EvidenceItem] = []
    kms_items: list[EvidenceItem] = []
    request_context = _extract_s3_request_context(evidence)

    for item in evidence:
        source_lower = (item.source or "").lower()
        description_lower = (item.description or "").lower()
        obs_lower = (item.observation or "").lower()
        if "accessdenied" in obs_lower or "access denied" in obs_lower:
            access_denied_items.append(item)
        if (
            "get-bucket-policy" in source_lower
            or "bucket-policy" in source_lower
            or "bucket policy" in description_lower
        ):
            bucket_policy_items.append(item)
        if "no identity-based policy" in obs_lower or "not authorized to perform" in obs_lower:
            iam_items.append(item)
        if "kms" in obs_lower and ("kms:decrypt" in obs_lower or "kms exception" in obs_lower):
            kms_items.append(item)

    if access_denied_items:
        findings.append(Finding(
            description="Amazon S3 API returned 403 AccessDenied response.",
            status=FindingStatus.OBSERVED.value,
            evidence_ids=[item.id for item in access_denied_items],
            explanation=(
                "S3 rejected the request. Possible causes include bucket or identity policies, "
                "SCPs, Block Public Access, or KMS permissions; the response alone does not identify the cause."
            ),
        ))

    for policy_item in bucket_policy_items:
        payload = _extract_json_payload(policy_item.observation or "")
        if not isinstance(payload, dict) or "Statement" not in payload:
            findings.append(Finding(
                description="Bucket policy could not be parsed as complete JSON.",
                status=FindingStatus.NEEDS_INVESTIGATION.value,
                evidence_ids=[policy_item.id],
                explanation="Retrieve the complete policy JSON. Text fragments are insufficient to evaluate statement applicability.",
            ))
            continue

        raw_statements = payload["Statement"]
        statements = raw_statements if isinstance(raw_statements, list) else [raw_statements]
        deny_statements = [
            statement for statement in statements
            if isinstance(statement, dict) and str(statement.get("Effect", "")).lower() == "deny"
        ]
        if not deny_statements:
            findings.append(Finding(
                description="No explicit Deny statement was found in the inspected bucket policy.",
                status=FindingStatus.OBSERVED.value,
                evidence_ids=[policy_item.id],
                explanation="Continue investigating identity policies, KMS permissions, SCPs, Block Public Access, and other applicable policies.",
            ))
            continue

        matched_deny = False
        uncertain_deny = False
        for statement in deny_statements:
            sid = str(statement.get("Sid", "ExplicitDeny"))
            applies, reason = _evaluate_s3_deny_statement(statement, request_context)
            if applies is True:
                matched_deny = True
                secure_transport_false = False
                condition = statement.get("Condition", {})
                if isinstance(condition, dict) and request_context.get("secure_transport") is False:
                    for operator, operands in condition.items():
                        if operator.lower() == "bool" and isinstance(operands, dict):
                            for key, value in operands.items():
                                if key.lower() == "aws:securetransport" and str(value).lower() == "false":
                                    secure_transport_false = True
                vpce_expected = None
                if isinstance(condition, dict):
                    for _operator, operands in condition.items():
                        if isinstance(operands, dict):
                            for key, value in operands.items():
                                if key.lower() == "aws:sourcevpce":
                                    values = _policy_values(value)
                                    if values:
                                        vpce_expected = values[0]
                if secure_transport_false:
                    denial_description = (
                        f"Bucket policy statement '{sid}' explicitly denies the observed S3 request "
                        "(unencrypted HTTP; explicit Deny applies)."
                    )
                elif vpce_expected:
                    denial_description = (
                        f"Bucket policy statement '{sid}' explicitly denies the observed S3 request "
                        f"(explicit Deny condition for VPC endpoint '{vpce_expected}')."
                    )
                else:
                    denial_description = (
                        f"Bucket policy statement '{sid}' explicitly denies the observed S3 request "
                        "(explicit Deny applies)."
                    )
                findings.append(Finding(
                    description=denial_description,
                    status=FindingStatus.CONFIRMED.value,
                    evidence_ids=[policy_item.id] + list(request_context["context_evidence_ids"]),
                    explanation=(
                        "The supported action, resource, principal, and condition checks match the request evidence. "
                        "This is a limited policy check, not a full AWS IAM evaluation."
                    ),
                ))
            elif applies is None:
                uncertain_deny = True
                findings.append(Finding(
                    description=f"Bucket policy statement '{sid}' may deny the observed request; applicability is not fully established.",
                    status=FindingStatus.SUPPORTED.value,
                    evidence_ids=[policy_item.id] + list(request_context["context_evidence_ids"]),
                    explanation=f"{reason} Collect the missing request details or use an AWS policy evaluation tool.",
                ))
            elif "aws:SecureTransport" in reason and request_context.get("secure_transport") is True:
                findings.append(Finding(
                    description=f"Bucket policy statement '{sid}' enforces TLS, and the observed request used HTTPS.",
                    status=FindingStatus.OBSERVED.value,
                    evidence_ids=[policy_item.id],
                    explanation="This condition does not explain an AccessDenied response for the HTTPS request.",
                ))

        if not matched_deny and not uncertain_deny and not any(
            finding.evidence_ids == [policy_item.id]
            and finding.status == FindingStatus.OBSERVED.value
            for finding in findings
        ):
            findings.append(Finding(
                description="No inspected bucket-policy Deny statement was shown to match the request evidence.",
                status=FindingStatus.OBSERVED.value,
                evidence_ids=[policy_item.id],
                explanation="The available action, resource, principal, or condition data ruled out the inspected Deny statements; investigate other policy layers.",
            ))

    for item in iam_items:
        findings.append(Finding(
            description="Evidence indicates the caller lacks a required identity-based permission.",
            status=FindingStatus.SUPPORTED.value,
            evidence_ids=[item.id],
            explanation="Verify the caller identity, action, resource, and applicable identity policy.",
        ))

    for item in kms_items:
        findings.append(Finding(
            description="Evidence indicates a possible KMS decryption permission problem.",
            status=FindingStatus.SUPPORTED.value,
            evidence_ids=[item.id],
            explanation="Verify the KMS key policy, grants, identity policy, and the actual operation required.",
        ))

    if not findings:
        findings.append(Finding(
            description="Insufficient evidence to evaluate S3 access denial.",
            status=FindingStatus.NEEDS_INVESTIGATION.value,
            explanation="Capture the exact S3 API operation, target resource, caller context, and complete bucket policy.",
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
