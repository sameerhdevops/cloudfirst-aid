# Runbook: EC2 SSH Connection Times Out (CFA-001)

## 1. Problem
An application engineer or DevOps team member reports:
> "I cannot SSH into our production bastion or application server (`203.0.113.10`). My terminal hangs for a minute and then says 'Connection timed out'. I need to deploy an emergency hotfix immediately."

## 2. What the Engineer Sees
```text
$ ssh -v -i ~/.ssh/prod-bastion.pem ec2-user@203.0.113.10
OpenSSH_8.9p1 Ubuntu-3ubuntu0.6, OpenSSL 3.0.2 15 Mar 2022
debug1: Connecting to 203.0.113.10 [203.0.113.10] port 22.
debug1: connect to address 203.0.113.10 port 22: Connection timed out
ssh: connect to host 203.0.113.10 port 22: Connection timed out
```
In the AWS Management Console:
- The instance state shows **running** (green indicator).
- Status checks show **2/2 checks passed**.

## 3. Before Changing Anything
Establish these facts first:
1. **Never reboot or stop/start the instance blindly.** Rebooting changes ephemeral public IPs (unless Elastic IP is assigned) and destroys valuable in-memory diagnostic state.
2. Verify your **own current public IP** address. Public IPs from home/office ISPs or VPNs fluctuate. A security group rule tied to an outdated IP is the #1 cause of sudden SSH dropouts.
3. Determine whether AWS Systems Manager (SSM) Session Manager is available as an alternate, out-of-band management channel.

## 4. Investigation Sequence

### Step 1: Confirm Your Current Public IP (Read-only Diagnostic)
- **Why it matters:** Security Groups enforce IP-based ingress filters.
- **Command:**
  ```bash
  curl -s https://checkip.amazonaws.com
  ```
- **Interpretation:** Note this IP address (e.g., `198.51.100.45`). Compare it with the Security Group ingress rules in Step 2.

### Step 2: Inspect Inbound Security Group Rules for Port 22 (Read-only Diagnostic)
- **Why it matters:** Security Groups are stateful firewalls evaluated at the AWS hypervisor before packets reach the instance operating system.
- **Command:**
  ```bash
  aws ec2 describe-security-groups \
    --group-ids sg-0123456789abcdef0 \
    --query "SecurityGroups[*].IpPermissions[?ToPort==\`22\`]" \
    --output json
  ```
- **What to look for:**
  - An entry where `FromPort: 22`, `ToPort: 22`, and `IpProtocol: tcp`.
  - Check the `IpRanges`: Does it include your current public IP address (`198.51.100.45/32`)?
  - If no rule exists, or the CIDR block does not cover your IP, traffic is dropped silently without an ICMP reject packet (causing a timeout).
- **Next check:** If Security Group rule is correct, check Subnet Route Table (Step 3).

### Step 3: Verify Subnet Route Table Has Route to Internet Gateway (Read-only Diagnostic)
- **Why it matters:** For an EC2 instance to be reachable from the public internet, its subnet must have a direct route to an Internet Gateway (`igw-xxxx`).
- **Command:**
  ```bash
  aws ec2 describe-route-tables \
    --filters "Name=association.subnet-id,Values=subnet-0123456789abcdef0" \
    --query "RouteTables[*].Routes" \
    --output table
  ```
- **What to look for:** A route with `DestinationCidrBlock: 0.0.0.0/0` and `GatewayId: igw-xxxxxxxx`.
- **Next check:** If route table points to a `nat-xxxx`, this instance is located in a private subnet and cannot receive inbound internet connections.

### Step 4: Check Subnet Network Access Control Lists (NACLs) (Read-only Diagnostic)
- **Why it matters:** Unlike Security Groups, NACLs are **stateless**. Both inbound and outbound rules must allow the traffic.
- **Command:**
  ```bash
  aws ec2 describe-network-acls \
    --filters "Name=association.subnet-id,Values=subnet-0123456789abcdef0" \
    --output json
  ```
- **What to look for:**
  - Inbound rule: Rule number lower than `*` (Deny) allowing TCP port 22.
  - Outbound rule: Rule allowing TCP ports `1024-65535` (ephemeral return traffic). If outbound ephemeral traffic is blocked, client connection hangs.

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| Security Group missing port 22 rule for client IP | **High** | `describe-security-groups` lacks client IP/CIDR; timeout occurs immediately. |
| Subnet Route Table missing Internet Gateway (IGW) | **Medium** | Route table shows no `0.0.0.0/0 -> igw-xxx`. |
| NACL blocking outbound ephemeral return traffic | **Low** | Inbound rule exists, but outbound NACL only allows port 80/443. |
| Local OS firewall (iptables/ufw) blocking port 22 | **Low** | Requires connecting via SSM Session Manager or Serial Console to verify. |

## 6. Remediation

### If Security Group Rule is Missing (AWS Infrastructure Change):
Add an ingress rule authorizing TCP port 22 from your specific IP:
```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-0123456789abcdef0 \
  --protocol tcp \
  --port 22 \
  --cidr 198.51.100.45/32
```

### If Subnet Missing Internet Gateway Route (AWS Infrastructure Change):
Add default route to the subnet's route table:
```bash
aws ec2 create-route \
  --route-table-id rtb-0123456789abcdef0 \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id igw-0123456789abcdef0
```

## 7. Verification
Run verbose SSH to confirm connection:
```bash
ssh -v -i ~/.ssh/prod-bastion.pem ec2-user@203.0.113.10
```
Expected output:
```text
debug1: Connection established.
debug1: Local version string SSH-2.0-OpenSSH_8.9p1
...
debug1: Authentication succeeded (publickey).
```

## 8. Prevention & Best Practices
1. **Adopt AWS Systems Manager Session Manager:** Connect to instances without opening port 22 in Security Groups, eliminating internet-facing attack surfaces entirely.
2. **Never open port 22 to `0.0.0.0/0`:** Always restrict ingress to corporate VPN or bastion IP CIDRs.
3. **Use EC2 Instance Connect Endpoints (EICE):** Provides secure SSH connectivity without public IPv4 addresses or internet gateways.

## 9. Interview Discussion Points
- **Q: How do you differentiate between an SSH timeout and an SSH "Connection refused"?**
  - *Answer:* A **timeout** means packets are dropped along the network path (Security Group drop, missing route table IGW entry, or NACL drop). A **connection refused** means the network path is open and packets reached the server OS, but no process is listening on TCP port 22 (sshd service stopped or bound to localhost).
- **Q: Why must NACL rules explicitly allow return traffic for SSH?**
  - *Answer:* Security Groups are stateful (they automatically track connections and allow return traffic), whereas NACLs are stateless. Return packets use ephemeral ports (1024-65535) chosen by the client OS, so NACL outbound rules must permit them.

## 10. References
- [AWS EC2: Troubleshooting connecting to your instance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/TroubleshootingInstancesConnecting.html)
- [AWS VPC: Security Groups and Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html)
- `man 1 ssh`
