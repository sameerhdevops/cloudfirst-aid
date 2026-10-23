# Runbook: Private Subnet Cannot Access Internet via NAT Gateway (CFA-018)

## 1. Problem
An engineer working on an EC2 instance in a private VPC subnet reports:
> "I am connected to our private database or worker instance via Systems Manager Session Manager, but I cannot download software packages or call third-party APIs. Running `curl https://aws.amazon.com` or `yum update` completely hangs and times out."

## 2. What the Engineer Sees
From inside the private instance:
```bash
$ curl -Iv --connect-timeout 5 https://aws.amazon.com
* Trying 54.239.30.25:443...
* Connection timed out after 5001 milliseconds
* Closing connection 0
curl: (28) Connection timed out after 5001 milliseconds
```
Ping to external IPs also times out:
```bash
$ ping -c 3 8.8.8.8
PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
--- 8.8.8.8 ping statistics ---
3 packets transmitted, 0 received, 100% packet loss, time 2048ms
```

## 3. Before Changing Anything
1. **Understand VPC routing fundamentals:** An instance in a private subnet cannot reach the internet unless:
   - Private subnet Route Table routes `0.0.0.0/0` to a **NAT Gateway** (`nat-xxxx`).
   - The NAT Gateway itself is placed in a **public subnet**.
   - The public subnet's Route Table routes `0.0.0.0/0` to an **Internet Gateway** (`igw-xxxx`).
   - The NAT Gateway has an **Elastic IP (EIP)** attached and is in `available` state.
2. If ANY link in this chain is broken, outbound traffic drops.

## 4. Investigation Sequence

### Step 1: Inspect the Private Subnet Route Table (Read-only Diagnostic)
- **Command:**
  ```bash
  aws ec2 describe-route-tables \
    --filters "Name=association.subnet-id,Values=subnet-private123" \
    --query "RouteTables[*].Routes" \
    --output json
  ```
- **What to look for:**
  - An entry for `DestinationCidrBlock: 0.0.0.0/0`.
  - Is `NatGatewayId` specified?
  - *Common Bug:* The route table only contains the local VPC CIDR (`10.0.0.0/16 -> local`), with no default route at all!

### Step 2: Verify NAT Gateway State and Attached Elastic IP (Read-only Diagnostic)
- **Command:**
  ```bash
  aws ec2 describe-nat-gateways \
    --nat-gateway-ids nat-0123456789abcdef0 \
    --query "NatGateways[*].[State,SubnetId,NatGatewayAddresses[*].PublicIp]" \
    --output json
  ```
- **What to look for:**
  - `State`: Must be `available`. If `pending`, `deleting`, or `failed`, outbound traffic will fail.
  - Check the `SubnetId` hosting the NAT Gateway (e.g., `subnet-public456`). Note this subnet ID for Step 3.

### Step 3: Verify NAT Gateway Subnet is Genuinely Public (Read-only Diagnostic)
- **Why it matters:** The #1 architectural mistake is creating a NAT Gateway inside the private subnet it was meant to serve! A NAT Gateway located in a subnet without an Internet Gateway cannot route outbound packets.
- **Command:**
  ```bash
  aws ec2 describe-route-tables \
    --filters "Name=association.subnet-id,Values=subnet-public456" \
    --query "RouteTables[*].Routes" \
    --output table
  ```
- **What to look for:**
  - The subnet hosting the NAT Gateway MUST have a route `0.0.0.0/0 -> igw-xxxxxxxx`.
  - If the NAT Gateway's own subnet lacks an IGW route, the NAT Gateway is isolated and non-functional.

### Step 4: Verify Subnet Network ACLs (Read-only Diagnostic)
- Check if NACLs associated with either the private subnet or the NAT Gateway's subnet are blocking outbound traffic or return ephemeral traffic (`1024-65535`).

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| Private Route Table missing default route to NAT GW | **High** | `describe-route-tables` shows only `10.0.0.0/16 -> local`. |
| NAT Gateway placed in a private subnet (no IGW) | **High** | NAT Gateway's subnet route table lacks `igw-xxx`. |
| NAT Gateway in `failed` or `deleted` state | **Low** | `describe-nat-gateways` shows `State: failed`. |
| Security Group egress rule missing | **Low** | Private instance SG has no outbound rule for 0.0.0.0/0. |

## 6. Remediation

### If Private Route Table Missing NAT Route (AWS Infrastructure Change):
Add default route targeting the NAT Gateway:
```bash
aws ec2 create-route \
  --route-table-id rtb-private123 \
  --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id nat-0123456789abcdef0
```

### If NAT Gateway Was Launched in the Wrong Subnet (AWS Infrastructure Change):
1. Allocate an Elastic IP:
   ```bash
   aws ec2 allocate-address --domain vpc
   ```
2. Create a new NAT Gateway in the verified **public subnet**:
   ```bash
   aws ec2 create-nat-gateway \
     --subnet-id subnet-public-verified \
     --allocation-id eipalloc-0123456789abcdef0
   ```
3. Wait for state to become `available`:
   ```bash
   aws ec2 wait nat-gateway-available --nat-gateway-ids nat-new
   ```
4. Update the private route table to point to `nat-new`.
5. Delete the old misconfigured NAT Gateway to avoid hourly charges.

## 7. Verification
From the private EC2 instance:
```bash
curl -Iv https://checkip.amazonaws.com
```
Expected output:
```text
* Connected to checkip.amazonaws.com port 443
...
< HTTP/1.1 200 OK
52.204.12.34
```
*Note:* The IP returned should match the Elastic IP associated with your NAT Gateway!

## 8. Prevention & Best Practices
1. **Use VPC Reachability Analyzer:** Run an automated path analysis from the private EC2 network interface (`eni-private`) to the Internet Gateway (`igw-xxxx`) before deploying workloads.
2. **Use VPC Endpoints for AWS Services:** For Amazon S3 and DynamoDB, use Gateway VPC Endpoints (free of charge); traffic routes directly across the AWS network without traversing the NAT Gateway.

## 9. Interview Discussion Points
- **Q: Can you associate a Security Group directly with a NAT Gateway?**
  - *Answer:* No. AWS Managed NAT Gateways do not support Security Groups. Security at the NAT layer is controlled exclusively via Network ACLs (NACLs) attached to the public subnet where the NAT Gateway resides.
- **Q: What is the pricing impact of routing S3 traffic through a NAT Gateway?**
  - *Answer:* NAT Gateways charge both an hourly rate and a per-GB data processing fee. Pushing large backups or datasets to S3 through a NAT Gateway generates substantial data transfer costs. Creating a free S3 Gateway VPC Endpoint keeps S3 traffic on internal AWS routing with zero data processing fees.

## 10. References
- [AWS VPC: NAT gateway troubleshooting](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-troubleshooting.html)
- [AWS VPC: Gateway VPC endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html)
