"""Optional read-only AWS diagnostic inspector.

SAFETY & DESIGN INVARIANTS:
1. Offline-first: The package works 100% without boto3 or AWS credentials.
2. Zero side-effects: Read-only APIs exclusively (Describe*, Get*). Never modifies state.
3. Explicit invocation only: Never triggered automatically during import, test, or local triage.
4. Safe data handling: Sanitizes and redacts credentials, sensitive keys, and tokens.
"""

from __future__ import annotations

import json

from cloudfirst_aid.evidence import redact_sensitive_fields
from cloudfirst_aid.models import EvidenceItem


def is_boto3_available() -> bool:
    """Check if boto3 is installed in the active environment."""
    try:
        import boto3  # noqa: F401
        return True
    except ImportError:
        return False


def inspect_ec2_instance_readonly(instance_id: str, region_name: str | None = None) -> list[EvidenceItem]:
    """Inspect EC2 instance state and attached security groups in read-only mode.

    Returns EvidenceItem list if successful. Raises RuntimeError on missing boto3 or AWS errors.
    """
    if not is_boto3_available():
        raise RuntimeError(
            "Optional dependency 'boto3' is not installed. "
            "Install with: pip install cloudfirst-aid[aws] or pip install boto3"
        )

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    evidence: list[EvidenceItem] = []

    try:
        session = boto3.Session(region_name=region_name)
        ec2 = session.client("ec2")

        # 1. Describe Instance
        res = ec2.describe_instances(InstanceIds=[instance_id])
        reservations = res.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            raise ValueError(f"Instance {instance_id} was not found in region {session.region_name}.")

        inst = reservations[0]["Instances"][0]
        state = inst.get("State", {}).get("Name", "unknown")
        vpc_id = inst.get("VpcId", "none")
        subnet_id = inst.get("SubnetId", "none")
        public_ip = inst.get("PublicIpAddress", "none")
        private_ip = inst.get("PrivateIpAddress", "none")
        sgs = [sg.get("GroupId") for sg in inst.get("SecurityGroups", [])]

        obs_summary = {
            "InstanceId": instance_id,
            "State": state,
            "VpcId": vpc_id,
            "SubnetId": subnet_id,
            "PublicIp": public_ip,
            "PrivateIp": private_ip,
            "SecurityGroupIds": sgs,
        }

        evidence.append(EvidenceItem(
            id=f"LIVE-AWS-EC2-{instance_id}-STATE",
            scenario_id="CFA-001",
            description=f"EC2 Instance State and Network Metadata for {instance_id}",
            source="ec2:DescribeInstances",
            observation=redact_sensitive_fields(json.dumps(obs_summary, indent=2)),
            provenance="live_aws",
            limitations="Live API query reflects snapshot at collection moment.",
        ))

        # 2. Describe Security Groups
        if sgs:
            sg_res = ec2.describe_security_groups(GroupIds=sgs)
            sg_rules = []
            for sg in sg_res.get("SecurityGroups", []):
                for rule in sg.get("IpPermissions", []):
                    sg_rules.append({
                        "GroupId": sg.get("GroupId"),
                        "IpProtocol": rule.get("IpProtocol"),
                        "FromPort": rule.get("FromPort"),
                        "ToPort": rule.get("ToPort"),
                        "IpRanges": [r.get("CidrIp") for r in rule.get("IpRanges", [])],
                    })

            evidence.append(EvidenceItem(
                id=f"LIVE-AWS-EC2-{instance_id}-SG",
                scenario_id="CFA-001",
                description=f"Attached Security Group Inbound Rules for {instance_id}",
                source="ec2:DescribeSecurityGroups",
                observation=redact_sensitive_fields(json.dumps(sg_rules, indent=2)),
                provenance="live_aws",
                limitations="Does not evaluate NACLs, OS firewall (iptables/ufw), or route tables.",
            ))

        return evidence

    except (BotoCoreError, ClientError) as err:
        raise RuntimeError(f"AWS Read-Only API call failed: {redact_sensitive_fields(str(err))}") from err
