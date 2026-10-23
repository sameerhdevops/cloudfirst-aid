"""Unit tests for optional read-only AWS inspection (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cloudfirst_aid.aws_readonly import (
    inspect_ec2_instance_readonly,
    is_boto3_available,
)


def test_boto3_availability_check() -> None:
    """Verify boto3 availability check returns boolean without error."""
    result = is_boto3_available()
    assert isinstance(result, bool)


def test_inspect_ec2_without_boto3() -> None:
    """Verify informative error message when boto3 is not installed."""
    with patch("cloudfirst_aid.aws_readonly.is_boto3_available", return_value=False):
        with pytest.raises(RuntimeError) as exc:
            inspect_ec2_instance_readonly("i-0123456789abcdef0")
        assert "boto3" in str(exc.value)


def test_inspect_ec2_mocked_success() -> None:
    """Verify read-only EC2 inspection parses responses into EvidenceItems."""
    mock_boto3 = MagicMock()
    mock_session = MagicMock()
    mock_ec2 = MagicMock()

    mock_boto3.Session.return_value = mock_session
    mock_session.client.return_value = mock_ec2
    mock_session.region_name = "us-east-1"

    # Mock describe_instances
    mock_ec2.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-0123456789abcdef0",
                        "State": {"Name": "running"},
                        "VpcId": "vpc-12345678",
                        "SubnetId": "subnet-12345678",
                        "PublicIpAddress": "203.0.113.10",
                        "PrivateIpAddress": "10.0.1.50",
                        "SecurityGroups": [{"GroupId": "sg-12345678"}],
                    }
                ]
            }
        ]
    }

    # Mock describe_security_groups
    mock_ec2.describe_security_groups.return_value = {
        "SecurityGroups": [
            {
                "GroupId": "sg-12345678",
                "IpPermissions": [
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 80,
                        "ToPort": 80,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    }
                ],
            }
        ]
    }

    with (
        patch("cloudfirst_aid.aws_readonly.is_boto3_available", return_value=True),
        patch.dict("sys.modules", {"boto3": mock_boto3, "botocore.exceptions": MagicMock()}),
    ):
        evidence = inspect_ec2_instance_readonly("i-0123456789abcdef0", region_name="us-east-1")

    assert len(evidence) == 2
    assert all(e.provenance == "live_aws" for e in evidence)
    assert any("STATE" in e.id for e in evidence)
    assert any("SG" in e.id for e in evidence)
