# Runbook: Application Load Balancer Unhealthy Targets (CFA-017)

## 1. Problem
Clients accessing an application through an AWS Application Load Balancer (ALB) receive:
```text
HTTP 502 Bad Gateway
```
or
```text
HTTP 503 Service Unavailable: Back-end server is at capacity
```
In the AWS Console, the ALB Target Group shows **0 healthy targets**. All registered EC2 instances display **Status: Unhealthy**.

## 2. What the Engineer Sees
Querying target health via AWS CLI:
```json
{
  "TargetHealthDescriptions": [
    {
      "Target": {"Id": "i-0123456789abcdef0", "Port": 8080},
      "HealthCheckPort": "8080",
      "TargetHealth": {
        "State": "unhealthy",
        "Reason": "Target.Timeout",
        "Description": "Connection to target timed out while health checking"
      }
    }
  ]
}
```
Or in another incident:
```json
{
  "TargetHealth": {
    "State": "unhealthy",
    "Reason": "Target.ResponseCodeMismatch",
    "Description": "Health checks failed with these codes: [404]"
  }
}
```

## 3. Before Changing Anything
1. **Notice the Target Health Reason code:** AWS explicitly tells you why the health check failed. Do not guess!
   - `Target.Timeout`: Network connectivity / Security Group firewall dropping probe packets.
   - `Target.ResponseCodeMismatch`: Network works, but web server returns a status code (e.g. 404, 301, 500) outside the configured matcher.
   - `Target.FailedConnection`: Connection refused (target is not listening on that port or web server crashed).
2. Confirm whether the backend EC2 instances are in `running` state with 2/2 status checks passed.

## 4. Investigation Sequence

### Step 1: Query Target Health and Specific Reason Codes (Read-only Diagnostic)
- **Command:**
  ```bash
  aws elbv2 describe-target-health \
    --target-group-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/app-tg/1234567890abcdef
  ```
- **Interpretation:**
  - If `Reason: Target.Timeout` -> Proceed to Step 2 (Security Group & Network).
  - If `Reason: Target.ResponseCodeMismatch` -> Proceed to Step 3 (Application Endpoint).
  - If `Reason: Target.FailedConnection` -> Proceed to Step 4 (Instance Port Listening).

### Step 2: Diagnose `Target.Timeout` (Read-only Diagnostic - Security Group Ingress)
- **Why it matters:** The target EC2 instances MUST permit incoming traffic from the ALB's Security Group on the target port (e.g., 8080).
- **Check ALB Security Group:**
  ```bash
  aws elbv2 describe-load-balancers \
    --names my-alb \
    --query "LoadBalancers[*].SecurityGroups"
  ```
  Note the ALB SG ID (e.g., `sg-alb123456`).
- **Check Target Instance Security Group:**
  ```bash
  aws ec2 describe-security-groups \
    --group-ids sg-target-instance \
    --query "SecurityGroups[*].IpPermissions"
  ```
- **What to look for:**
  - Does an inbound rule exist on port 8080 with `UserIdGroupPairs.GroupId: sg-alb123456`?
  - If missing, the target drops health check packets, resulting in `Target.Timeout`.

### Step 3: Diagnose `Target.ResponseCodeMismatch` (Read-only Diagnostic)
- **Why it matters:** The Target Group configuration expects specific HTTP status codes (default `200`).
- **Check Configured Health Check Path:**
  ```bash
  aws elbv2 describe-target-groups \
    --target-group-arns arn:aws:elasticloadbalancing:... \
    --query "TargetGroups[*].[HealthCheckPath,Matcher.HttpCode]"
  ```
- **Test Directly from within VPC:**
  Log into an EC2 instance inside the VPC and probe the target:
  ```bash
  curl -Iv http://10.0.1.50:8080/healthz
  ```
- **What to look for:**
  - If it returns `HTTP/1.1 404 Not Found`: The health check path does not exist in the application router.
  - If it returns `HTTP/1.1 301 Moved Permanently`: The app redirects HTTP to HTTPS, but the health check probe doesn't follow redirects!

### Step 4: Diagnose `Target.FailedConnection` (Read-only Diagnostic)
- Log into the target instance:
  ```bash
  sudo ss -tlnp | grep ':8080'
  ```
- If no process is listening on `:8080`, or it is bound only to `127.0.0.1:8080` (loopback), the ALB cannot connect to it on its private IP.

## 5. Remediation

### If Security Group Rule is Missing (Target.Timeout) (AWS Infrastructure Change):
Authorize the ALB Security Group to access the target instance port:
```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-target-instance \
  --protocol tcp \
  --port 8080 \
  --source-group sg-alb123456
```

### If Health Check Path Mismatch (Target.ResponseCodeMismatch):
Update the Target Group health check path:
```bash
aws elbv2 modify-target-group \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --health-check-path /api/health
```
Or allow 200 and 301 responses:
```bash
aws elbv2 modify-target-group \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --matcher "HttpCode=200,301"
```

## 6. Verification
Monitor target health:
```bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --query "TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]" \
  --output table
```
Expected output:
```text
--------------------------------
|     DescribeTargetHealth     |
+----------------------+-------+
|  i-0123456789abcdef0 |healthy|
+----------------------+-------+
```
Then test accessing the ALB DNS name:
```bash
curl -I http://my-alb-123456.us-east-1.elb.amazonaws.com
# Returns HTTP/1.1 200 OK
```

## 7. Prevention & Best Practices
1. **Reference Security Groups by ID:** Never use hardcoded private CIDRs for ALB-to-instance security rules; always reference the ALB Security Group ID.
2. **Dedicated `/healthz` endpoint:** Maintain a lightweight, static health check route that does not depend on database or external microservice connections.

## 8. Interview Discussion Points
- **Q: What is the difference between an HTTP 502 and HTTP 504 on an Application Load Balancer?**
  - *Answer:* A **502 Bad Gateway** means the ALB connected to the target, but the target closed the connection prematurely (TCP RST), returned an empty response, or returned malformed HTTP headers. A **504 Gateway Timeout** means the connection was established, but the target failed to finish sending the response within the ALB idle timeout window (default 60 seconds).
- **Q: How does ALB health check deregistration work?**
  - *Answer:* When a target is marked unhealthy or is deregistered, the ALB stops routing new connections to it and enters a "deregistration delay" (connection draining) period (default 300 seconds), allowing in-flight requests to complete before terminating connections.

## 9. References
- [AWS ELB: Target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html)
- [AWS ELB: Troubleshoot your Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-troubleshooting.html)
