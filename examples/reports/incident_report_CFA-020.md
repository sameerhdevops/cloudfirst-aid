# Incident Investigation Report: CFA-020

**Title:** S3 AccessDenied 403 / Bucket Policy Explicit Deny  
**Category:** Iam-s3 | **Severity:** HIGH | **Difficulty:** Intermediate  
**Generated:** 2026-10-23 06:54:21 UTC  
**Investigating Agent / Operator:** CloudFirst Aid Diagnostic Engine  

---

## 1. Incident Overview

**Reported Symptom:**  
> IAM principal receives 'An error occurred (AccessDenied) when calling the GetObject operation' accessing S3 bucket.

**Initial Observations:**
- Principal has AdministratorAccess IAM policy attached.
- Request is still denied by Amazon S3.

**Target Environment / Prerequisites:**  
Amazon S3 bucket with Bucket Policy.

## 2. Diagnostic Evidence & Provenance

> **Provenance Summary:** 2 Simulated Fixtures | 0 Local System Checks | 0 Live AWS Observations

### Evidence Item 1: `SIM-EVID-CFA020-01` (SIMULATED)
- **Description:** AWS S3 CLI operation error response
- **Source Command / API:** `aws s3 cp s3://company-prod-data/financials.csv .`
- **Recorded At:** Fixture / Undated

```text
fatal error: An error occurred (AccessDenied) when calling the GetObject operation: Access Denied
```

> **Known Limitation:** Standard S3 AccessDenied response returned to IAM caller.

### Evidence Item 2: `SIM-EVID-CFA020-02` (SIMULATED)
- **Description:** S3 Bucket Policy inspection
- **Source Command / API:** `aws s3api get-bucket-policy --bucket company-prod-data --output text`
- **Recorded At:** Fixture / Undated

```text
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUnencryptedTraffic",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::company-prod-data",
        "arn:aws:s3:::company-prod-data/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    },
    {
      "Sid": "RestrictToVpcEndpoint",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::company-prod-data/*",
      "Condition": {
        "StringNotEquals": {
          "aws:sourceVpce": "vpce-1a2b3c4d"
        }
      }
    }
  ]
}
```

> **Known Limitation:** Bucket policy enforces an explicit Deny for any request not originating from VPC Endpoint vpce-1a2b3c4d.

## 3. Triage & Diagnostic Findings

Evaluation of evidence against deterministic troubleshooting rules:

### Finding 1: [OBSERVED] S3 returned 403 AccessDenied response.
- **Status:** `observed`
- **Supporting Evidence:** SIM-EVID-CFA020-01
- **Diagnostic Explanation:** The S3 service rejected the API call. Possible causes include IAM policy, bucket policy explicit Deny, S3 Block Public Access, or KMS permissions.

### Finding 2: [CONFIRMED] S3 Bucket Policy contains an explicit Deny statement.
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA020-02
- **Diagnostic Explanation:** An explicit Deny in an S3 bucket policy unconditionally overrides any IAM Allow. Requests not satisfying the condition block (e.g. source VPC endpoint or HTTPS) are blocked.

## 4. Remediation Guidance

Recommended corrective actions based on candidate root causes:

### If Cause is: Explicit Deny statement in the S3 Bucket Policy overrides IAM Allow (Likelihood: common)
**Required Evidence to Confirm:** Bucket policy contains Statement with Effect: Deny matching principal or missing Condition exception.

**Remediation Steps:**
Audit bucket policy conditions (e.g. aws:PrincipalArn, aws:sourceVpce, aws:SecureTransport) and update.

### If Cause is: S3 Block Public Access enabled at account or bucket level blocking access (Likelihood: common)
**Required Evidence to Confirm:** GetPublicAccessBlock returns BlockPublicPolicy: true.

**Remediation Steps:**
Review and configure Block Public Access settings if public/cross-account access was intended.

## 5. Verification & Prevention

**Verification Procedure:**  
Run `aws s3 cp s3://my-bucket/test.txt .` and confirm download succeeds.

**Prevention & Monitoring Best Practices:**
- Use IAM Policy Simulator to test policy evaluations before deploying bucket policies.
- Always include NotPrincipal or Condition exclusions when using broad Deny statements.

## 6. Official References

- [https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-access-denied.html](https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-access-denied.html)

---
_Report compiled by CloudFirst Aid — offline-first AWS & Linux support diagnostic lab._
