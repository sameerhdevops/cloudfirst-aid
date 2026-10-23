# Runbook: EC2 Instance Permissions for S3 (CFA-006)

## 1. Problem
An application deployed on an Amazon EC2 instance attempts to interact with an S3 bucket (e.g., uploading data files, reading application assets) and fails with:
```text
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```
Or when AWS CLI is run on the instance:
```text
fatal error: An error occurred (AccessDenied) when calling the ListObjectsV2 operation: Access Denied
```

## 2. What the Engineer Sees
From inside the EC2 instance:
```bash
$ aws s3 ls s3://my-company-app-assets/
fatal error: An error occurred (AccessDenied) when calling the ListObjectsV2 operation: Access Denied
```
Checking AWS STS caller identity:
```bash
$ aws sts get-caller-identity
```
- Case A: Returns `Unable to locate credentials`.
- Case B: Returns an IAM assumed-role ARN, but specific S3 actions are forbidden.

## 3. Before Changing Anything
1. **Never store static AWS Access Keys in `~/.aws/credentials` on an EC2 instance.** Storing static keys introduces high security risk and breaks credential rotation standards. The official AWS architecture pattern is an **IAM Role for EC2** attached via an **Instance Profile**.
2. Understand the **credential precedence order** evaluated by the AWS SDK / CLI:
   1. Command-line flags (`--profile`).
   2. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
   3. Web identity token / ECS credentials.
   4. Shared credentials file (`~/.aws/credentials`).
   5. **EC2 Instance Metadata Service (IMDS)** credentials.
   *Notice:* If someone previously placed static dummy keys in environment variables or `~/.aws/credentials`, the SDK will use those broken keys and ignore the attached IAM Instance Profile!

## 4. Investigation Sequence

### Step 1: Check If Instance Profile is Attached to the EC2 Instance
- **Command:**
  ```bash
  aws ec2 describe-instances \
    --instance-ids i-0123456789abcdef0 \
    --query "Reservations[*].Instances[*].IamInstanceProfile" \
    --output json
  ```
- **What to look for:**
  - If output is `[[]]` or `null`: No IAM role is attached to the instance! -> Proceed to Remediation Step A.
  - If an `Arn` is listed: Note the instance profile name and proceed to Step 2.

### Step 2: Query Instance Metadata Service (IMDSv2) Directly
- **Why it matters:** Verify that the guest operating system can communicate with the AWS hypervisor metadata service (`169.254.169.254`) and retrieve temporary STS credentials.
- **Commands (IMDSv2):**
  ```bash
  # Step 1: Retrieve session token
  TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")

  # Step 2: Query IAM security credentials endpoint
  curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/
  ```
- **Interpretation:**
  - If this returns HTTP 401 or hangs: Check local iptables firewall or IMDSv2 configuration (`HttpEndpoint=enabled`).
  - If it returns the role name (e.g. `AppS3AccessRole`): IMDS credential vending is working properly.

### Step 3: Check Active Caller Identity vs Environment Overrides
- **Command:**
  ```bash
  env | grep AWS
  aws sts get-caller-identity
  ```
- **What to look for:**
  - Does `env` contain hardcoded `AWS_ACCESS_KEY_ID`?
  - Does `aws sts get-caller-identity` show `assumed-role/AppS3AccessRole/i-0123456789abcdef0`?

### Step 4: Audit the IAM Role Policy Syntax for S3 Actions
- **Why it matters:** S3 permissions require different resource ARNs for bucket-level actions versus object-level actions:
  - `s3:ListBucket` requires the **bucket ARN**: `arn:aws:s3:::my-company-app-assets`
  - `s3:GetObject`, `s3:PutObject` require the **wildcard object ARN**: `arn:aws:s3:::my-company-app-assets/*`
  - *Common Bug:* An IAM policy that grants `s3:*` on `arn:aws:s3:::my-bucket/*` will FAIL when calling `aws s3 ls s3://my-bucket` because `s3:ListBucket` is evaluated against the bucket ARN, not the object wildcard!

## 5. Remediation

### Action A: Create and Attach IAM Instance Profile
If no role was attached:
```bash
# 1. Create instance profile
aws iam create-instance-profile --instance-profile-name EC2-S3-AppProfile

# 2. Add role to instance profile
aws iam add-role-to-instance-profile \
  --instance-profile-name EC2-S3-AppProfile \
  --role-name AppS3AccessRole

# 3. Associate instance profile with running instance
aws ec2 associate-iam-instance-profile \
  --instance-id i-0123456789abcdef0 \
  --iam-instance-profile Name=EC2-S3-AppProfile
```

### Action B: Fix IAM Policy Resource ARNs
Attach a policy covering both bucket and object actions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBucketListing",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::my-company-app-assets"
    },
    {
      "Sid": "AllowObjectOperations",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::my-company-app-assets/*"
    }
  ]
}
```

### Action C: Clear Overriding Environment Variables
```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE
```

## 6. Verification
From the EC2 instance:
```bash
aws s3 ls s3://my-company-app-assets/
echo "healthcheck" > /tmp/test.txt
aws s3 cp /tmp/test.txt s3://my-company-app-assets/test.txt
aws s3 rm s3://my-company-app-assets/test.txt
```
All commands succeed without error.

## 7. Prevention & Best Practices
1. **Enforce IMDSv2:** Set `--http-tokens required` on all EC2 instances to prevent SSRF vulnerabilities from leaking IAM credentials.
2. **Least Privilege:** Always scope IAM policies to specific bucket ARNs; never use `"Resource": "*"` for S3 write permissions.

## 8. Interview Discussion Points
- **Q: Why does `s3:ListBucket` require `arn:aws:s3:::bucket` while `s3:GetObject` requires `arn:aws:s3:::bucket/*`?**
  - *Answer:* In S3's resource hierarchy, the bucket itself is the resource being queried when listing keys (`s3:ListBucket`). Individual data payloads stored inside the bucket are distinct object resources (`s3:GetObject`), which reside under the bucket's namespace path (`bucket/*`).
- **Q: What is the purpose of an IAM Instance Profile?**
  - *Answer:* An instance profile is an AWS container for an IAM role that allows Amazon EC2 to pass the role credentials to the instance. In the AWS Management Console, creating a role for EC2 automatically generates an instance profile with the same name, but via the AWS CLI or Terraform, the instance profile must be created and linked explicitly.

## 9. References
- [AWS EC2: IAM roles for Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
- [AWS S3: Troubleshoot Access Denied errors](https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-access-denied.html)
