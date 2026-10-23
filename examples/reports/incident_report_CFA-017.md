# Incident Investigation Report: CFA-017

**Title:** Application Load Balancer Reports Unhealthy Targets  
**Category:** Networking | **Severity:** CRITICAL | **Difficulty:** Intermediate  
**Generated:** 2026-10-23 06:54:21 UTC  
**Investigating Agent / Operator:** CloudFirst Aid Diagnostic Engine  

---

## 1. Incident Overview

**Reported Symptom:**  
> ALB target group shows all registered targets with Status: 'Unhealthy' and reason 'Target.Timeout' or 'Target.ResponseCodeMismatch'.

**Initial Observations:**
- ALB returns HTTP 502 or 503 to web clients.
- Targets are in running state in EC2 console.

**Target Environment / Prerequisites:**  
AWS ALB routing to EC2 target group.

## 2. Diagnostic Evidence & Provenance

> **Provenance Summary:** 2 Simulated Fixtures | 0 Local System Checks | 0 Live AWS Observations

### Evidence Item 1: `SIM-EVID-CFA017-01` (SIMULATED)
- **Description:** Application Load Balancer target health query
- **Source Command / API:** `aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/web-targets/abcdef123456`
- **Recorded At:** Fixture / Undated

```text
{
  "TargetHealthDescriptions": [
    {
      "Target": {"Id": "i-0123456789abcdef0", "Port": 8080},
      "TargetHealth": {
        "State": "unhealthy",
        "Reason": "Target.Timeout",
        "Description": "Connection to target timed out while health checking"
      }
    },
    {
      "Target": {"Id": "i-0fedcba9876543210", "Port": 8080},
      "TargetHealth": {
        "State": "unhealthy",
        "Reason": "Target.Timeout",
        "Description": "Connection to target timed out while health checking"
      }
    }
  ]
}
```

> **Known Limitation:** ALB reports all target instances unhealthy due to Target.Timeout.

### Evidence Item 2: `SIM-EVID-CFA017-02` (SIMULATED)
- **Description:** Target Security Group ingress configuration
- **Source Command / API:** `aws ec2 describe-security-groups --group-ids sg-target-instance`
- **Recorded At:** Fixture / Undated

```text
[
  {
    "GroupId": "sg-target-instance",
    "GroupName": "app-target-sg",
    "IpPermissions": [
      {
        "FromPort": 22,
        "ToPort": 22,
        "IpProtocol": "tcp",
        "IpRanges": [{"CidrIp": "10.0.0.0/16"}]
      }
    ]
  }
]
```

> **Known Limitation:** Target instance security group completely lacks an inbound rule for port 8080 from the ALB security group.

## 3. Triage & Diagnostic Findings

Evaluation of evidence against deterministic troubleshooting rules:

### Finding 1: [CONFIRMED] Target instances are reported as Unhealthy by Application Load Balancer.
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA017-01
- **Diagnostic Explanation:** Target group health checks are failing. The ALB cannot route traffic to targets, resulting in HTTP 502/503 responses returned to clients.

### Finding 2: [SUPPORTED] ALB health check failure reason is Target.Timeout.
- **Status:** `supported`
- **Supporting Evidence:** SIM-EVID-CFA017-01
- **Diagnostic Explanation:** Target.Timeout indicates the health check probes are not receiving TCP/HTTP responses before the timeout threshold. Usually caused by Security Group misconfiguration or routing.

### Finding 3: [CONFIRMED] Target Security Group does not authorize traffic on application port (8080).
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA017-02
- **Diagnostic Explanation:** The target EC2 security group only allows SSH (port 22) and lacks an ingress rule for port 8080 from the ALB security group.

## 4. Remediation Guidance

Recommended corrective actions based on candidate root causes:

### If Cause is: Target Security Group blocks traffic coming from the ALB Security Group (Likelihood: common)
**Required Evidence to Confirm:** Health check reason is Target.Timeout; EC2 SG has no inbound rule for ALB SG.

**Remediation Steps:**
Add an inbound rule to target SG permitting traffic on target port with source set to ALB Security Group ID.

### If Cause is: Health check path returns HTTP status outside the configured matcher (e.g. 404 or 301 vs expected 200) (Likelihood: common)
**Required Evidence to Confirm:** Health check reason is Target.ResponseCodeMismatch [status: 404].

**Remediation Steps:**
Update Target Group health check path to a valid endpoint or update application routing.

## 5. Verification & Prevention

**Verification Procedure:**  
Target health transitions to 'healthy' in `describe-target-health`.

**Prevention & Monitoring Best Practices:**
- Dedicate a lightweight `/healthz` endpoint returning HTTP 200 that does not require database access or authentication.
- Use Security Group reference rules instead of static CIDR ranges.

## 6. Official References

- [https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html)

---
_Report compiled by CloudFirst Aid — offline-first AWS & Linux support diagnostic lab._
