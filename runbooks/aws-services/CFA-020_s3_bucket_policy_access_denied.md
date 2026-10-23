# Runbook: S3 Bucket AccessDenied 403 / Explicit Deny (CFA-020)

## 1. Problem
An administrator or authorized IAM principal attempts to download or list an S3 bucket:
```text
$ aws s3 cp s3://company-prod-data/reports/q3.pdf .
fatal error: An error occurred (AccessDenied) when calling the GetObject operation: Access Denied
```
The caller has `AdministratorAccess` or explicit S3 full access in their identity policy, but S3 consistently rejects the request with HTTP 403 Forbidden.

## 2. What the Engineer Sees
```bash
$ aws s3 ls s3://company-prod-data/
fatal error: An error occurred (AccessDenied) when calling the ListObjectsV2 operation: Access Denied
```
Checking IAM identity policy via AWS CLI confirms the user has full permissions:
```json
{
  "Effect": "Allow",
  "Action": "s3:*",
  "Resource": "*"
}
```
Yet every access attempt is rejected.

## 3. Before Changing Anything
1. **Understand AWS Policy Evaluation Logic:** In AWS IAM, policy evaluation follows strict hierarchy:
   - **Explicit Deny ALWAYS wins:** If ANY policy (IAM Identity policy, S3 Bucket Policy, AWS Organizations Service Control Policy (SCP), or VPC Endpoint Policy) contains a statement with `"Effect": "Deny"`, that Deny immediately overrides every `"Effect": "Allow"`, regardless of administrator privileges.
   - An explicit Deny in an S3 Bucket Policy will block even the AWS Account Root User (unless edited by root or admin who modifies the bucket policy).
2. Look for common security policies:
   - Enforce HTTPS (`aws:SecureTransport: false`).
   - Enforce VPC Endpoint (`aws:sourceVpce`).
   - Enforce IP Whitelisting (`aws:SourceIp`).
   - S3 Block Public Access (BPA).

## 4. Investigation Sequence

### Step 1: Inspect the S3 Bucket Policy (Read-only Diagnostic)
- **Why it matters:** S3 Bucket Policies are resource-based policies attached directly to the bucket.
- **Command:**
  ```bash
  aws s3api get-bucket-policy \
    --bucket company-prod-data \
    --query Policy \
    --output text | jq .
  ```
- **What to look for in output:**
  Look for statements with `"Effect": "Deny"`:
  ```json
  {
    "Sid": "EnforceVpcEndpointOnly",
    "Effect": "Deny",
    "Principal": "*",
    "Action": "s3:*",
    "Resource": "arn:aws:s3:::company-prod-data/*",
    "Condition": {
      "StringNotEquals": {
        "aws:sourceVpce": "vpce-1a2b3c4d5e"
      }
    }
  }
  ```
- **Interpretation:** This policy explicitly denies ANY request that does not originate from VPC Endpoint `vpce-1a2b3c4d5e`. When accessed from home, public internet, or a different VPC, the request is unconditionally denied!

### Step 2: Check for Unencrypted Traffic Enforcement (`aws:SecureTransport`) (Read-only Diagnostic)
- **What to look for:**
  ```json
  {
    "Sid": "AllowSSLRequestsOnly",
    "Effect": "Deny",
    "Principal": "*",
    "Action": "s3:*",
    "Resource": "arn:aws:s3:::company-prod-data/*",
    "Condition": {
      "Bool": {
        "aws:SecureTransport": "false"
      }
    }
  }
  ```
- **Interpretation:** If an SDK or script sends plain HTTP requests (e.g. `endpoint_url="http://s3.amazonaws.com"`), S3 rejects the call.

### Step 3: Check S3 Block Public Access Settings (Read-only Diagnostic)
- **Command:**
  ```bash
  aws s3api get-public-access-block \
    --bucket company-prod-data
  ```
- **What to look for:** If `BlockPublicPolicy` or `RestrictPublicBuckets` is `true`, bucket policies granting access to `"Principal": "*"` without strict conditions are blocked.

### Step 4: Check for AWS Organizations Service Control Policies (SCPs) (Read-only Diagnostic)
- If the account belongs to AWS Organizations, an SCP at the Root or OU level may deny S3 actions in specific regions or on specific buckets.

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| Bucket policy contains explicit Deny with VPC/IP condition | **High** | `get-bucket-policy` shows `Effect: Deny` and `StringNotEquals: aws:sourceVpce`. |
| IAM policy missing specific resource ARN | **Medium** | Identity policy lacks `arn:aws:s3:::bucket/*`. |
| S3 Object encrypted with KMS key and caller lacks `kms:Decrypt` | **Medium** | Caller can list bucket, but `GetObject` on specific file returns AccessDenied. |
| AWS Organizations SCP explicit Deny | **Low** | All users in the account are blocked regardless of IAM role. |

## 6. Remediation

### If Explicit Deny Restricts Traffic to VPC Endpoint (AWS Infrastructure Change):
Option 1: Access the bucket from an EC2 instance or Lambda function inside the authorized VPC that routes through `vpce-1a2b3c4d5e`.
Option 2: If administrator emergency access is required, update the bucket policy to exclude specific administrative IAM roles using `ArnNotEquals`:
```json
{
  "Sid": "EnforceVpcEndpointExceptAdmin",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::company-prod-data",
    "arn:aws:s3:::company-prod-data/*"
  ],
  "Condition": {
    "StringNotEquals": {
      "aws:sourceVpce": "vpce-1a2b3c4d5e"
    },
    "ArnNotEquals": {
      "aws:PrincipalArn": "arn:aws:iam::123456789012:role/EmergencyAdminRole"
    }
  }
}
```

### Apply Updated Policy:
```bash
aws s3api put-bucket-policy \
  --bucket company-prod-data \
  --policy file://updated-policy.json
```

## 7. Verification
Run the S3 command from an authorized source or role:
```bash
aws s3 cp s3://company-prod-data/reports/q3.pdf .
```
Expected output:
```text
download: s3://company-prod-data/reports/q3.pdf to ./q3.pdf
```

## 8. Prevention & Best Practices
1. **Never use unqualified `"Principal": "*"` with `"Effect": "Deny"` without testing:** Always include condition exemptions for deployment roles or emergency administration.
2. **Test using IAM Policy Simulator:** Use the AWS IAM Policy Simulator to simulate the combination of Identity policies, Bucket policies, and SCPs before applying changes to production.

## 9. Interview Discussion Points
- **Q: In AWS IAM evaluation, what happens if an Identity Policy allows `s3:GetObject` but the S3 Bucket Policy does not mention the user?**
  - *Answer:* For requests within the **same AWS account**, an explicit Allow in EITHER the Identity-based policy OR the Resource-based policy is sufficient to grant access (provided there is no explicit Deny). For **cross-account** requests, BOTH the Identity policy in the caller account AND the Bucket policy in the resource account must explicitly grant access.
- **Q: Can the AWS Account Root User be locked out by an S3 Bucket Policy with an explicit Deny?**
  - *Answer:* While the root user's data access requests (e.g. `s3:GetObject`) will be denied by an explicit Deny in a bucket policy, the root user retains the hardcoded permission to execute `s3:DeleteBucketPolicy` and `s3:PutBucketPolicy` to remove the offending policy and recover access.

## 10. References
- [AWS S3: Troubleshooting Access Denied (403 Forbidden) errors](https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-access-denied.html)
- [AWS IAM: Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
