# Incident Investigation Report: CFA-001

**Title:** EC2 SSH Connection Times Out  
**Category:** Ec2 | **Severity:** HIGH | **Difficulty:** Beginner  
**Generated:** 2026-10-23 06:53:32 UTC  
**Investigating Agent / Operator:** CloudFirst Aid Diagnostic Engine  

---

## 1. Incident Overview

**Reported Symptom:**  
> Engineer attempts to connect to an Amazon EC2 instance via SSH (`ssh -i key.pem ec2-user@203.0.113.10`) and receives: 'ssh: connect to host 203.0.113.10 port 22: Connection timed out'.

**Initial Observations:**
- SSH client hangs for approximately 30-60 seconds before printing 'Connection timed out'.
- The instance shows 'running' state in the AWS Management Console.
- No TCP handshake is completed.

**Target Environment / Prerequisites:**  
Amazon Linux 2 / 2023 EC2 instance in a public subnet with an attached Elastic IP.

## 2. Diagnostic Evidence & Provenance

> **Provenance Summary:** 3 Simulated Fixtures | 0 Local System Checks | 0 Live AWS Observations

### Evidence Item 1: `SIM-EVID-CFA001-01` (SIMULATED)
- **Description:** Verbose OpenSSH client connection trace
- **Source Command / API:** `ssh -vvv -i mykey.pem ec2-user@203.0.113.10`
- **Recorded At:** Fixture / Undated

```text
OpenSSH_8.9p1 Ubuntu-3ubuntu0.6, OpenSSL 3.0.2 15 Mar 2022
debug1: Connecting to 203.0.113.10 [203.0.113.10] port 22.
debug1: connect to address 203.0.113.10 port 22: Connection timed out
ssh: connect to host 203.0.113.10 port 22: Connection timed out
```

> **Known Limitation:** Simulated SSH client failure output representing typical TCP connection timeout.

### Evidence Item 2: `SIM-EVID-CFA001-02` (SIMULATED)
- **Description:** AWS EC2 instance state query
- **Source Command / API:** `aws ec2 describe-instances --instance-ids i-0123456789abcdef0 --query 'Reservations[0].Instances[0].State.Name'`
- **Recorded At:** Fixture / Undated

```text
"running"
```

> **Known Limitation:** Simulated EC2 describe-instances response confirming instance is booted.

### Evidence Item 3: `SIM-EVID-CFA001-03` (SIMULATED)
- **Description:** Security Group ingress rules evaluation
- **Source Command / API:** `aws ec2 describe-security-groups --group-ids sg-0123456789abcdef0 --query 'SecurityGroups[0].IpPermissions'`
- **Recorded At:** Fixture / Undated

```text
[
  {
    "FromPort": 80,
    "IpProtocol": "tcp",
    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
    "ToPort": 80
  }
]
```

> **Known Limitation:** Security Group only permits port 80. Port 22 has no rule; inbound SSH traffic is dropped.

## 3. Triage & Diagnostic Findings

Evaluation of evidence against deterministic troubleshooting rules:

### Finding 1: [OBSERVED] SSH connection is timing out.
- **Status:** `observed`
- **Supporting Evidence:** SIM-EVID-CFA001-01
- **Diagnostic Explanation:** The TCP handshake never completes. The packet is being dropped.

### Finding 2: [OBSERVED] EC2 instance is in running state.
- **Status:** `observed`
- **Supporting Evidence:** SIM-EVID-CFA001-02
- **Diagnostic Explanation:** The virtual machine is powered on; failure is occurring at network/firewall layer.

### Finding 3: [CONFIRMED] Security group does not allow inbound SSH on port 22.
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA001-03
- **Diagnostic Explanation:** The security group attached to the instance has no rule authorizing TCP port 22 ingress. Traffic is silently dropped by the AWS hypervisor.

## 4. Remediation Guidance

Recommended corrective actions based on candidate root causes:

### If Cause is: Security Group does not permit inbound TCP port 22 from the engineer's public IP (Likelihood: common)
**Required Evidence to Confirm:** ec2:DescribeSecurityGroups showing no rule for port 22 or CIDR mismatch.

**Remediation Steps:**
Add an inbound rule to the instance's Security Group authorizing TCP port 22 from your specific IP/32.

### If Cause is: Subnet Route Table missing route to Internet Gateway (0.0.0.0/0 -> igw-xxx) (Likelihood: common)
**Required Evidence to Confirm:** ec2:DescribeRouteTables showing no default 0.0.0.0/0 route to an attached IGW.

**Remediation Steps:**
Attach an Internet Gateway to the VPC and add route 0.0.0.0/0 pointing to the IGW ID.

### If Cause is: Network ACL (NACL) blocking inbound port 22 or outbound ephemeral ports (1024-65535) (Likelihood: occasional)
**Required Evidence to Confirm:** ec2:DescribeNetworkAcls showing a Deny rule before Allow or missing outbound return rule.

**Remediation Steps:**
Update subnet NACL to allow inbound port 22 and outbound ephemeral ports (1024-65535).

## 5. Verification & Prevention

**Verification Procedure:**  
Execute `ssh -v -i key.pem ec2-user@<public-ip>` and confirm the TCP handshake succeeds (OpenSSH banner exchange starts).

**Prevention & Monitoring Best Practices:**
- Use AWS Systems Manager (SSM) Session Manager for shell access without exposing port 22 to the public internet.
- Use EC2 Instance Connect with specific IP prefixes or client VPN.

## 6. Official References

- [https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/TroubleshootingInstancesConnecting.html](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/TroubleshootingInstancesConnecting.html)
- [https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html)

---
_Report compiled by CloudFirst Aid — offline-first AWS & Linux support diagnostic lab._
