"""Unit tests for the diagnostic triage engine."""

from __future__ import annotations

import json

from cloudfirst_aid.evidence import load_evidence_fixtures
from cloudfirst_aid.models import FindingStatus
from cloudfirst_aid.triage import has_triage_rules, triage_scenario


def test_triage_rule_registration() -> None:
    """Verify registered status for all 6 demo scenarios."""
    registered = ["CFA-001", "CFA-010", "CFA-011", "CFA-013", "CFA-017", "CFA-020"]
    for sid in registered:
        assert has_triage_rules(sid) is True
    assert has_triage_rules("CFA-999") is False


def test_triage_cfa001_ssh_timeout() -> None:
    """CFA-001: SSH Connection Timeout triage rules."""
    evidence = load_evidence_fixtures("CFA-001")
    assert len(evidence) == 3

    findings = triage_scenario("CFA-001", evidence)
    assert len(findings) >= 2

    # Check observed vs confirmed distinction
    statuses = {f.status for f in findings}
    assert FindingStatus.OBSERVED.value in statuses
    assert FindingStatus.CONFIRMED.value in statuses

    # Confirm Security Group rule violation is detected
    sg_finding = next((f for f in findings if "security group" in f.description.lower()), None)
    assert sg_finding is not None
    assert sg_finding.status == FindingStatus.CONFIRMED.value


def test_triage_cfa010_disk_full() -> None:
    """CFA-010: Linux Root Filesystem Full triage rules."""
    evidence = load_evidence_fixtures("CFA-010")
    assert len(evidence) == 3

    findings = triage_scenario("CFA-010", evidence)
    assert any(f.status == FindingStatus.CONFIRMED.value and "100%" in f.description for f in findings)
    assert any(f.status == FindingStatus.POSSIBLE.value and "/var/log" in f.explanation for f in findings)


def test_triage_cfa011_inode_exhaustion() -> None:
    """CFA-011: Linux Inode Exhaustion triage rules."""
    evidence = load_evidence_fixtures("CFA-011")
    assert len(evidence) == 2

    findings = triage_scenario("CFA-011", evidence)
    assert any(f.status == FindingStatus.CONFIRMED.value and "inodes" in f.description.lower() for f in findings)


def test_triage_cfa013_service_failure() -> None:
    """CFA-013: systemd Service Failure / Address Already in Use."""
    evidence = load_evidence_fixtures("CFA-013")
    assert len(evidence) == 3

    findings = triage_scenario("CFA-013", evidence)
    assert any(f.status == FindingStatus.CONFIRMED.value and "failed state" in f.description.lower() for f in findings)
    assert any("already in use" in f.description.lower() for f in findings)


def test_triage_cfa017_alb_unhealthy() -> None:
    """CFA-017: ALB Unhealthy Targets."""
    evidence = load_evidence_fixtures("CFA-017")
    assert len(evidence) == 2

    findings = triage_scenario("CFA-017", evidence)
    assert any(f.status == FindingStatus.CONFIRMED.value and "unhealthy" in f.description.lower() for f in findings)
    assert any("8080" in f.description for f in findings)


def test_triage_cfa020_s3_explicit_deny() -> None:
    """CFA-020: S3 AccessDenied / Bucket Policy Explicit Deny."""
    evidence = load_evidence_fixtures("CFA-020")
    assert len(evidence) == 3

    findings = triage_scenario("CFA-020", evidence)
    assert any(f.status == FindingStatus.OBSERVED.value and "accessdenied" in f.description.lower() for f in findings)
    assert any(f.status == FindingStatus.CONFIRMED.value and "explicit deny" in f.description.lower() for f in findings)


def test_triage_unknown_scenario() -> None:
    """Verify unknown scenarios return a graceful needs-investigation finding."""
    findings = triage_scenario("CFA-999", [])
    assert len(findings) == 1
    assert findings[0].status == FindingStatus.NEEDS_INVESTIGATION.value


def test_triage_empty_evidence() -> None:
    """Verify all scenarios handle empty evidence by returning NEEDS_INVESTIGATION."""
    scenarios = ["CFA-001", "CFA-010", "CFA-011", "CFA-013", "CFA-017", "CFA-020"]
    for sid in scenarios:
        findings = triage_scenario(sid, [])
        assert len(findings) >= 1
        assert any(f.status == FindingStatus.NEEDS_INVESTIGATION.value for f in findings)


def test_triage_disk_full_no_false_positive_on_unrelated_percentage() -> None:
    """Verify unrelated percentages like 89% or non-table 95% confidence don't trigger 100% full."""
    from cloudfirst_aid.models import EvidenceItem

    fake_evidence = [
        EvidenceItem(
            id="E1",
            scenario_id="CFA-010",
            description="Confidence score",
            source="custom-tool",
            observation="Model evaluated with 95% confidence. Filesystem /dev/xvda1 has 85% usage.",
            provenance="simulated",
        )
    ]
    findings = triage_scenario("CFA-010", fake_evidence)
    # Must NOT claim 100% capacity
    assert not any("100%" in f.description for f in findings)
    assert not any(f.status == FindingStatus.CONFIRMED.value for f in findings)


def test_triage_service_failure_ignores_generic_bind_word() -> None:
    """Verify that generic mentions of 'bind' without EADDRINUSE don't trigger port conflict."""
    from cloudfirst_aid.models import EvidenceItem

    fake_evidence = [
        EvidenceItem(
            id="E1",
            scenario_id="CFA-013",
            description="DNS server info",
            source="journalctl",
            observation="Started BIND DNS server daemon successfully on standard interfaces.",
            provenance="simulated",
        )
    ]
    findings = triage_scenario("CFA-013", fake_evidence)
    assert not any("already in use" in f.description.lower() for f in findings)


def test_triage_s3_allow_policy_does_not_trigger_deny() -> None:
    """Verify an Allow-only S3 bucket policy does not trigger confirmed explicit Deny finding."""
    from cloudfirst_aid.models import EvidenceItem

    fake_evidence = [
        EvidenceItem(
            id="E1",
            scenario_id="CFA-020",
            description="Bucket policy",
            source="aws s3api get-bucket-policy",
            observation='{"Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject"}]}',
            provenance="simulated",
        )
    ]
    findings = triage_scenario("CFA-020", fake_evidence)
    assert not any(f.status == FindingStatus.CONFIRMED.value and "deny" in f.description.lower() for f in findings)


def test_triage_s3_missing_caller_context_produces_supported() -> None:
    """Verify that when caller network context is unknown, policy Deny is SUPPORTED, not CONFIRMED."""
    from cloudfirst_aid.models import EvidenceItem

    policy = {
        "Statement": [
            {
                "Sid": "VpceOnly",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Condition": {
                    "StringNotEquals": {"aws:sourceVpce": "vpce-12345678"}
                },
            }
        ]
    }
    evidence = [
        EvidenceItem(
            id="E1",
            scenario_id="CFA-020",
            description="API Error",
            source="aws s3 cp",
            observation="An error occurred (AccessDenied) when calling the GetObject operation",
            provenance="simulated",
        ),
        EvidenceItem(
            id="E2",
            scenario_id="CFA-020",
            description="Bucket Policy",
            source="aws s3api get-bucket-policy",
            observation=str(policy).replace("'", '"'),
            provenance="simulated",
        ),
    ]
    findings = triage_scenario("CFA-020", evidence)
    # Without caller network context, cannot confirm if caller matched vpce-12345678 or not
    assert not any(f.status == FindingStatus.CONFIRMED.value and "vpce" in f.description.lower() for f in findings)
    assert any(f.status == FindingStatus.SUPPORTED.value and "vpce" in f.description.lower() for f in findings)


def test_triage_s3_string_equals_evaluation() -> None:
    """Verify StringEquals condition correctly identifies caller match or non-match."""
    from cloudfirst_aid.models import EvidenceItem

    policy_json = json.dumps({
        "Statement": [
            {
                "Sid": "DenySpecificVpce",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Condition": {
                    "StringEquals": {"aws:sourceVpce": "vpce-badendpoint"}
                },
            }
        ]
    })

    # Case A: Caller matched the denied endpoint
    evidence_match = [
        EvidenceItem("E1", "CFA-020", "Error", "aws s3 cp", "AccessDenied", "simulated"),
        EvidenceItem("E2", "CFA-020", "Policy", "aws s3api get-bucket-policy", policy_json, "simulated"),
        EvidenceItem("E3", "CFA-020", "Origin", "ec2-metadata", "Caller routed through vpce-badendpoint", "simulated"),
    ]
    findings_match = triage_scenario("CFA-020", evidence_match)
    assert any(f.status == FindingStatus.CONFIRMED.value and "vpce-badendpoint" in f.description for f in findings_match)

    # Case B: Caller did NOT match the denied endpoint
    evidence_different = [
        EvidenceItem("E1", "CFA-020", "Error", "aws s3 cp", "AccessDenied", "simulated"),
        EvidenceItem("E2", "CFA-020", "Policy", "aws s3api get-bucket-policy", policy_json, "simulated"),
        EvidenceItem("E3", "CFA-020", "Origin", "ec2-metadata", "Caller routed through vpce-othergood", "simulated"),
    ]
    findings_diff = triage_scenario("CFA-020", evidence_different)
    assert not any(f.status == FindingStatus.CONFIRMED.value and "vpce" in f.description.lower() for f in findings_diff)


def test_triage_s3_secure_transport_evaluation() -> None:
    """Verify aws:SecureTransport condition confirms on HTTP and observes on HTTPS."""
    from cloudfirst_aid.models import EvidenceItem

    policy_json = json.dumps({
        "Statement": [
            {
                "Sid": "DenyInsecure",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Condition": {
                    "Bool": {"aws:SecureTransport": "false"}
                },
            }
        ]
    })

    # HTTP caller -> CONFIRMED
    evidence_http = [
        EvidenceItem("E1", "CFA-020", "Error", "curl http://bucket.s3.amazonaws.com", "AccessDenied", "simulated"),
        EvidenceItem("E2", "CFA-020", "Policy", "aws s3api get-bucket-policy", policy_json, "simulated"),
    ]
    findings_http = triage_scenario("CFA-020", evidence_http)
    assert any(f.status == FindingStatus.CONFIRMED.value and "unencrypted http" in f.description.lower() for f in findings_http)

    # HTTPS caller -> OBSERVED (TLS used, so SecureTransport deny was not triggered)
    evidence_https = [
        EvidenceItem("E1", "CFA-020", "Error", "curl https://bucket.s3.amazonaws.com", "AccessDenied", "simulated"),
        EvidenceItem("E2", "CFA-020", "Policy", "aws s3api get-bucket-policy", policy_json, "simulated"),
    ]
    findings_https = triage_scenario("CFA-020", evidence_https)
    assert any(f.status == FindingStatus.OBSERVED.value and "enforces tls" in f.description.lower() for f in findings_https)


def test_triage_alb_dynamic_ports_and_source_sg() -> None:
    """Verify ALB triage derives ports dynamically and validates source security groups."""
    from cloudfirst_aid.models import EvidenceItem

    target_health = (
        'TargetHealthDescriptions: [{"Target": {"Id": "i-12345", "Port": 9000}, '
        '"TargetHealth": {"State": "unhealthy", "Reason": "Target.Timeout"}}]'
    )
    # Ingress rule allowing 8080 from ALB SG, but target is 9000
    sg_rules_wrong_port = (
        'SecurityGroupRules: [{"FromPort": 8080, "ToPort": 8080, "IpProtocol": "tcp", '
        '"ReferencedGroupId": "sg-alb123", "GroupId": "sg-app456"}]'
    )

    evidence = [
        EvidenceItem("E1", "CFA-017", "Health", "aws elbv2 describe-target-health", target_health, "simulated"),
        EvidenceItem("E2", "CFA-017", "SG", "aws ec2 describe-security-group-rules", sg_rules_wrong_port, "simulated"),
    ]
    findings = triage_scenario("CFA-017", evidence)
    assert any(f.status == FindingStatus.CONFIRMED.value and "port 9000" in f.description.lower() for f in findings)


def test_triage_alb_order_independence() -> None:
    """Verify evidence ordering does not affect findings produced by ALB triage."""
    evidence = load_evidence_fixtures("CFA-017")
    findings_forward = triage_scenario("CFA-017", evidence)
    findings_reversed = triage_scenario("CFA-017", list(reversed(evidence)))

    assert [f.description for f in findings_forward] == [f.description for f in findings_reversed]
    assert [f.status for f in findings_forward] == [f.status for f in findings_reversed]

