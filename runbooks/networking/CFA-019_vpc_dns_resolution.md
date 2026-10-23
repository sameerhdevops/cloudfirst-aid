# Runbook: VPC DNS Resolution Failure (CFA-019)

## 1. Problem
Applications running inside a newly created AWS VPC cannot resolve external domain names (`api.stripe.com`, `aws.amazon.com`) or private Route 53 DNS records.
Running `nslookup` or `dig` times out or fails with:
```text
;; connection timed out; no servers could be reached
```

## 2. What the Engineer Sees
From inside an EC2 instance:
```bash
$ ping -c 2 8.8.8.8
# Ping succeeds! Confirms IP routing and ICMP echo reachability,
# but does NOT verify DNS resolution, TCP port reachability, or upper-layer application health.

$ nslookup amazon.com
;; connection timed out; no servers could be reached
```
Checking `/etc/resolv.conf`:
```text
nameserver 10.0.0.2
```
Querying the local VPC resolver directly (`10.0.0.2` or `169.254.169.253`):
```bash
$ dig @10.0.0.2 amazon.com
;; connection timed out; no servers could be reached
```

## 3. Before Changing Anything
1. Notice that raw IP routing works (`ping 8.8.8.8` succeeded). The Internet Gateway, NAT Gateway, and routing tables are intact.
2. In AWS VPC, the Amazon DNS server (Route 53 Resolver) is located at the VPC network range plus two (`VPC CIDR base + 2`, e.g., `10.0.0.2` in a `10.0.0.0/16` VPC), as well as the link-local address `169.254.169.253`.
3. If the VPC attribute `enableDnsSupport` is disabled (`false`), AWS shuts down the Amazon Route 53 Resolver for that entire VPC.
4. **Architectural Note on NACLs and Route 53 Resolver:** The Amazon Route 53 Resolver (`VPC base + 2` and `169.254.169.253`) operates at the AWS hypervisor level. Subnet Network ACLs (NACLs) and Security Groups **do not** filter or block traffic to the Route 53 Resolver. However, if your instances query external or on-premises DNS servers (e.g., `8.8.8.8` or `192.168.1.10`), NACLs and Security Groups **do** apply and must permit outbound UDP/TCP 53 and inbound ephemeral return traffic.

## 4. Investigation Sequence

### Step 1: Check VPC DNS Attributes (Read-only Diagnostic)
- **Command:**
  ```bash
  aws ec2 describe-vpc-attribute \
    --vpc-id vpc-0123456789abcdef0 \
    --attribute enableDnsSupport

  aws ec2 describe-vpc-attribute \
    --vpc-id vpc-0123456789abcdef0 \
    --attribute enableDnsHostnames
  ```
- **What to look for in output:**
  ```json
  {
    "VpcId": "vpc-0123456789abcdef0",
    "EnableDnsSupport": {
      "Value": false
    }
  }
  ```
- **Interpretation:** If `EnableDnsSupport` is `false`, the VPC resolver at `10.0.0.2` will refuse and drop all UDP/TCP port 53 packets.

### Step 2: Check DHCP Options Set Configuration (Read-only Diagnostic)
- **Why it matters:** A custom DHCP option set may have instructed EC2 instances to use on-premises or invalid third-party DNS servers that are unreachable.
- **Command:**
  ```bash
  aws ec2 describe-vpcs \
    --vpc-ids vpc-0123456789abcdef0 \
    --query "Vpcs[*].DhcpOptionsId" \
    --output text
  ```
  Then inspect the DHCP options:
  ```bash
  aws ec2 describe-dhcp-options \
    --dhcp-options-ids dopt-0123456789abcdef0 \
    --output json
  ```
- **What to look for:** Does `domain-name-servers` contain `AmazonProvidedDNS`? If it lists custom IPs (e.g. `192.168.1.10`), verify if network routes exist to reach those corporate DNS servers.

### Step 3: Check External DNS Connectivity (Read-only Diagnostic, if using custom DNS)
- **Scope:** Relevant only when querying non-Amazon DNS servers (e.g. corporate forwarders or public resolvers like `8.8.8.8`).
- **Command:**
  ```bash
  # Check if custom DNS IP responds on UDP/TCP port 53:
  nc -zvu -w 3 8.8.8.8 53
  ```
- **Note:** Remember that Route 53 Resolver (`169.254.169.253` or VPC base+2) is never blocked by NACLs, but external DNS servers will be blocked if outbound NACL rules or Security Groups restrict UDP/TCP port 53.

## 5. Remediation

### If `enableDnsSupport` is Disabled (AWS Infrastructure Change):
Enable DNS support on the VPC:
```bash
aws ec2 modify-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --enable-dns-support '{"Value": true}'
```
Also enable DNS hostnames if instances require public DNS names:
```bash
aws ec2 modify-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --enable-dns-hostnames '{"Value": true}'
```

### If DHCP Option Set is Misconfigured (AWS Infrastructure Change & Local OS Restart):
Revert the VPC to use the default DHCP options set with `AmazonProvidedDNS`:
```bash
# Find default DHCP options ID:
aws ec2 describe-dhcp-options --filters "Name=key,Values=domain-name-servers" --query "DhcpOptions[*].[DhcpOptionsId,DhcpConfigurations]"

# Associate with VPC:
aws ec2 associate-dhcp-options \
  --dhcp-options-id default \
  --vpc-id vpc-0123456789abcdef0
```
On Linux instances (Local System Change), restart the networking daemon to pull updated DHCP leases:
```bash
sudo systemctl restart systemd-resolved  # On Ubuntu
# OR
sudo systemctl restart NetworkManager   # On RHEL/Amazon Linux
```

## 6. Verification
From inside the EC2 instance, test DNS lookups:
```bash
dig amazon.com +short
```
Expected output:
```text
205.251.242.103
54.239.28.85
52.94.236.248
```
Also verify private Route 53 hosted zones resolve correctly.

## 7. Prevention & Best Practices
1. **Terraform / CloudFormation defaults:** Always explicitly declare `enable_dns_support = true` and `enable_dns_hostnames = true` in custom VPC modules.
2. **Use Route 53 Resolver Inbound/Outbound Endpoints:** For hybrid cloud connectivity between AWS and on-premises data centers, use Route 53 Resolver Endpoints instead of hardcoding static DNS forwarders in DHCP option sets.

## 8. Interview Discussion Points
- **Q: What IP address does the Amazon-provided DNS server use in a VPC?**
  - *Answer:* It uses the reserved IP address at the base of the VPC CIDR plus two (`VPC CIDR + 2`, e.g., `172.31.0.2` in a `172.31.0.0/16` VPC), as well as the universal link-local IP `169.254.169.253`.
- **Q: What is the query rate limit of the Amazon Route 53 VPC Resolver?**
  - *Answer:* The Amazon Route 53 Resolver imposes a limit of **1024 packets per second (PPS)** per elastic network interface (ENI). Workloads that exceed this limit (such as intense microservice clusters or DNS crawlers) will experience DNS throttling and packet drops. The solution is to deploy local DNS caching daemons (like `dnsmasq` or `systemd-resolved`) on instances.

## 9. References
- [AWS VPC: DNS attributes in your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-dns.html)
- [AWS Route 53: Troubleshooting DNS resolution](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/troubleshooting-new-dns-settings-not-in-effect.html)
