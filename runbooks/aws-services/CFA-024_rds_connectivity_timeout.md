# Runbook: Application Cannot Connect to RDS Database (CFA-024)

## 1. Problem
An application deployed on Amazon EC2 crashes upon startup or during database connection pooling with:
```text
OperationalError: (2003, "Can't connect to MySQL server on 'prod-db.c12345678901.us-east-1.rds.amazonaws.com' (110)")
```
Or for PostgreSQL:
```text
psycopg2.OperationalError: could not connect to server: Connection timed out
        Is the server running on host "prod-db..." and accepting
        TCP/IP connections on port 5432?
```
The RDS instance state in the AWS Management Console displays **Available** (green).

## 2. What the Engineer Sees
From inside the EC2 application instance:
- Database connection attempts hang for 30 to 60 seconds before aborting with error `110: Connection timed out`.
- Testing low-level socket reachability via netcat:
  ```bash
  $ nc -zv -w 5 prod-db.c12345678901.us-east-1.rds.amazonaws.com 3306
  # No output for 5 seconds...
  nc: connect to prod-db.c12345678901.us-east-1.rds.amazonaws.com port 3306 (tcp) timed out: Operation now in progress
  ```

## 3. Before Changing Anything
1. **Notice the error code:** `110 Connection timed out` indicates a **network/firewall packet drop**. The TCP SYN packet was transmitted, but no response was received. This is NOT an authentication failure (`Access denied for user 'dbuser'@'%'`), and NOT a database crash.
2. Establish key network boundaries:
   - Is EC2 in the **same VPC** as RDS?
   - What **Security Group** is attached to the RDS DB instance?
   - Are EC2 and RDS in different subnets with route table or NACL boundaries?
   - Is "Publicly Accessible" relevant? (If EC2 is in the same VPC, "Publicly Accessible" should remain **No**; connections should route over internal private VPC network interfaces).

## 4. Investigation Sequence

### Step 1: Verify RDS DB Instance Endpoint and Port (Read-only Diagnostic)
- **Command:**
  ```bash
  aws rds describe-db-instances \
    --db-instance-identifier prod-db \
    --query "DBInstances[*].[Endpoint.Address,Endpoint.Port,DBSubnetGroup.VpcId,DBInstanceStatus]" \
    --output json
  ```
- **Interpretation:**
  - Verify `DBInstanceStatus` is `available`.
  - Confirm the exact port (`3306` for MySQL, `5432` for PostgreSQL).
  - Compare `VpcId` with the EC2 instance's `VpcId`.

### Step 2: Test Low-Level TCP Port Reachability (Read-only Diagnostic)
- **Why it matters:** Bypass application code and database drivers to test pure network connectivity.
- **Command (from EC2 instance):**
  ```bash
  nc -zv -w 5 <rds-endpoint> <port>
  # OR using bash built-in /dev/tcp:
  timeout 5 bash -c '</dev/tcp/<rds-endpoint>/<port>' && echo "PORT OPEN" || echo "PORT CLOSED/TIMED OUT"
  ```
- **Interpretation:** If timed out, the packet is blocked by Security Group, Route Table, or NACL.

### Step 3: Inspect RDS Security Group Ingress Rules (Read-only Diagnostic)
- **Why it matters:** The #1 root cause in cloud database connectivity is an RDS Security Group that does not authorize ingress from the EC2 instance's Security Group.
- **Find RDS Security Group ID:**
  ```bash
  aws rds describe-db-instances \
    --db-instance-identifier prod-db \
    --query "DBInstances[*].VpcSecurityGroups[*].VpcSecurityGroupId" \
    --output text
  ```
- **Inspect its Inbound Rules:**
  ```bash
  aws ec2 describe-security-groups \
    --group-ids sg-rds123456 \
    --query "SecurityGroups[*].IpPermissions" \
    --output json
  ```
- **What to look for:**
  - Is there an ingress rule on port `3306` (or `5432`)?
  - Does the rule permit traffic from the **EC2 instance's Security Group ID** (`sg-ec2app`)?
  - *Common Bug:* The rule only lists an outdated local IP or is completely empty!

### Step 4: Verify Subnet Routing and NACLs (Read-only Diagnostic)
- If EC2 and RDS are in different VPCs, is VPC Peering or Transit Gateway configured with bidirectional routing?
- Check Network ACLs on the database subnets to verify return ephemeral ports (`1024-65535`) are permitted.

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| RDS Security Group missing inbound rule for EC2 SG | **High** | RDS SG has no ingress rule for port 3306/5432; timeout occurs. |
| EC2 and RDS located in different VPCs without peering | **Medium** | `describe-db-instances` and `describe-instances` show different VPC IDs. |
| EC2 Security Group missing outbound rule | **Low** | EC2 SG has restrictive egress rules blocking port 3306. |
| Database connection pool exhausted (max_connections reached) | **Low** | Connection returns immediate error: `Too many connections` instead of timeout. |

## 6. Remediation

### Authorize EC2 Security Group in RDS Security Group (AWS Infrastructure Change)
Add an inbound rule to the RDS Security Group referencing the EC2 Security Group by ID:
```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-rds123456 \
  --protocol tcp \
  --port 3306 \
  --source-group sg-ec2app
```
*Best Practice:* Always use `--source-group` (Security Group reference) rather than static CIDR blocks. As EC2 instances auto-scale or relaunch with new private IPs, their Security Group membership guarantees continuous database connectivity.

## 7. Verification
From the EC2 instance, test port reachability:
```bash
nc -zv -w 5 prod-db.c12345678901.us-east-1.rds.amazonaws.com 3306
```
Expected output:
```text
Connection to prod-db.c12345678901.us-east-1.rds.amazonaws.com 3306 port [tcp/mysql] succeeded!
```
Now launch the application service:
```bash
sudo systemctl restart myapp.service
sudo systemctl status myapp.service
# Service enters active (running) state
```

## 8. Prevention & Best Practices
1. **Tiered Security Group Design:** Implement a standardized multi-tier architecture:
   - Web tier SG: Ingress 80/443 from ALB SG.
   - App tier SG: Ingress 8080 from Web/ALB SG.
   - Database tier SG: Ingress 3306/5432 from App tier SG only.
2. **Never open RDS database ports to `0.0.0.0/0`:** Keep RDS instances in private DB Subnet Groups with `PubliclyAccessible: false`.

## 9. Interview Discussion Points
- **Q: Why should you authorize a Security Group ID rather than a subnet CIDR for RDS access?**
  - *Answer:* Referencing a Security Group ID (e.g. `sg-app`) creates a dynamic micro-segmentation rule. Only EC2 instances explicitly assigned that specific security group can connect, regardless of which subnet or Availability Zone they reside in. In contrast, using a subnet CIDR grants access to any resource in that subnet, including unvetted or third-party VMs.
- **Q: What is the purpose of an RDS DB Subnet Group?**
  - *Answer:* A DB Subnet Group is a collection of subnets (typically private) spanning at least two distinct Availability Zones within a VPC. It dictates the VPC and IP subnets where RDS can provision the database's primary network interface and failover Multi-AZ replica interfaces.

## 10. References
- [AWS RDS: Troubleshooting connectivity](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Troubleshooting.html)
- [AWS VPC: Security Groups for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html)
