# The CloudFirst Aid Troubleshooting Methodology

This guide outlines the structured, evidence-based diagnostic methodology used by professional AWS Cloud Support and Linux Systems Engineers.

---

## The 6-Stage Troubleshooting Framework

```
[1. Intake & Scope]
         |
         v
[2. Diagnostic Baseline (Before Changing Anything)]
         |
         v
[3. Formulate & Test Hypotheses (Evidence Gathering)]
         |
         v
[4. Confirm Root Cause]
         |
         v
[5. Safe Remediation & Verification]
         |
         v
[6. Prevention & Post-Incident Review]
```

---

## Stage 1: Intake & Scope Verification
When an alert fires or a customer reports an incident:
- **Capture the exact symptom verbatim:** Do not rely on paraphrased summaries. Record the exact HTTP status code, SSH client error message, or systemd exit code.
- **Record the exact timestamp:** Cloud systems emit millions of metric and log points. Knowing the incident start time down to the minute enables targeted log slicing (`journalctl --since "10 minutes ago"`, CloudWatch Insights).
- **Define the blast radius:**
  - Is this affecting **one instance**, **one Availability Zone**, or the **entire VPC / Region**?
  - Is it affecting **all client requests** or only requests originating from specific IP ranges?

---

## Stage 2: Diagnostic Baseline (Before Changing Anything)
> **Cardinal Rule:** Establish the current diagnostic baseline before taking any action. Never reboot, restart daemons, or modify security group rules without capturing evidence first.

1. **Reboots destroy volatile diagnostic evidence:**
   - Linux kernel ring buffer (`dmesg`) records OOM-killer invocations, hardware faults, and filesystem errors.
   - Ephemeral public IPs on EC2 instances without Elastic IPs change upon instance stop/start.
   - Active TCP connection states (`ss -tan`, `lsof`) are wiped on reboot.
2. **Take snapshots where appropriate:** For corrupted filesystems or data partitions, create an EBS volume snapshot before attempting repair commands (`xfs_repair`, `fsck`).

---

## Stage 3: Formulate and Test Hypotheses
Work systematically from the physical / network layer up to the application layer (OSI model inverted for cloud):

### The 4 Network Checkpoints (For Reachability Issues):
1. **Host State:** Is the virtual machine running with passed status checks (`aws ec2 describe-instance-status`)?
2. **Security Group (Stateful Hypervisor Firewall):** Does an ingress rule exist authorizing the client's current public IP on the target port?
3. **Subnet Routing:** Does the subnet route table route `0.0.0.0/0` to an attached Internet Gateway (`igw-xxxx`) for public subnets, or a NAT Gateway (`nat-xxxx`) for private subnets?
4. **Network ACLs (Stateless Subnet Firewall):** Do both inbound AND outbound rules permit traffic (including ephemeral return ports `1024-65535`)?

### The Local Host Checkpoints (Inside Linux):
1. **Socket State (`ss -tlnp`):** Is the application daemon listening on the target port? Is it bound to `0.0.0.0` (all interfaces) or restricted to `127.0.0.1` (loopback only)?
2. **Storage Capacity (`df -h` and `df -i`):** Check both **block capacity** and **inode allocation**. A filesystem with 50GB free will still reject writes if inodes are 100% full.
3. **Process Health (`systemctl status`, `journalctl -u`):** Check the unit exit code (`status=1`, `status=127`, `status=137`).
4. **Memory & CPU (`free -h`, `top`, `dmesg`):** Inspect available RAM and scan for kernel OOM-killer actions.

---

## Stage 4: Distinguish Hypotheses from Confirmed Causes
In professional support reports, differentiate between:
- **Observed Fact:** What the diagnostic command directly reported (e.g. `df -h / shows 100% used`).
- **Possible Cause:** A plausible explanation that has not yet been verified (e.g. `Log files in /var/log may be unrotated`).
- **Supported Finding:** Evidence correlates with this hypothesis (e.g. `du -sh /var/log shows 16GB consumed out of 20GB`).
- **Confirmed Cause:** Direct, irrefutable evidence establishes this as the singular root cause (e.g. `app-debug.log is 14GB and unrotated`).

Never claim a root cause is "confirmed" until the specific evidence has been isolated.

---

## Stage 5: Safe Remediation and Verification
1. **Prefer reversible changes:** Add a new Security Group rule before deleting existing rules. Truncate an active log file (`truncate -s 0 file.log`) rather than deleting it while a process holds an open file descriptor.
2. **Execute one change at a time:** Applying multiple configuration edits simultaneously makes it impossible to determine which change fixed the problem or caused a secondary regression.
3. **Verify objectively:** Test the fix from the client perspective using direct probes (`curl -I`, `nc -zv`, `ssh -v`). Do not assume a service restart succeeded without running `systemctl is-active`.

---

## Stage 6: Prevention & Post-Incident Review
Troubleshooting does not end when service is restored. High-performing engineering teams address the systemic cause:
1. **Monitoring & Alarms:** Add CloudWatch metric alarms (e.g. alert when disk usage reaches 80% or ALB healthy targets drop below 2).
2. **Automated Recovery:** Attach EC2 auto-recovery actions to CloudWatch status check alarms.
3. **Runbook Updates:** Document the findings and diagnostic sequence so future engineers can resolve similar incidents in minutes.
