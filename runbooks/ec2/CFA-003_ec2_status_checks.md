# Runbook: EC2 Instance Fails Status Check (CFA-003)

## 1. Problem
A CloudWatch alarm fires or the EC2 console reports:
> "Status check failed" (1/2 or 0/2 checks passed) for critical production instance `i-0123456789abcdef0`.

The application on this instance is unresponsive and monitoring dashboards show flatlined metrics.

## 2. What the Engineer Sees
AWS CLI status check output:
```json
{
  "InstanceStatuses": [
    {
      "InstanceId": "i-0123456789abcdef0",
      "InstanceState": {"Name": "running"},
      "SystemStatus": {"Status": "impaired"},
      "InstanceStatus": {"Status": "passed"}
    }
  ]
}
```
Or in another incident:
```json
{
  "InstanceStatuses": [
    {
      "InstanceId": "i-0123456789abcdef0",
      "InstanceState": {"Name": "running"},
      "SystemStatus": {"Status": "passed"},
      "InstanceStatus": {"Status": "impaired"}
    }
  ]
}
```

## 3. Before Changing Anything
**Crucial Distinction:** Understand which specific status check has failed:
1. **System Status Check:** Monitors the AWS systems and physical hardware underlying your instance (power, network, host computer, hypervisor).
   - *Rule:* You cannot repair AWS hardware. A normal OS reboot within the instance will NOT fix this.
2. **Instance Status Check:** Monitors the software and network configuration of your individual instance (corrupted filesystem, kernel panic, `/etc/fstab` misconfiguration, exhausted memory/exhausted page table).
   - *Rule:* The issue is inside the guest OS. Stopping and starting may not fix it if boot configuration is corrupted.

## 4. Investigation Sequence

### Step 1: Query Specific Status Check Status
- **Command:**
  ```bash
  aws ec2 describe-instance-status \
    --instance-ids i-0123456789abcdef0 \
    --include-all-instances
  ```
- **Interpretation:**
  - If `SystemStatus.Status == "impaired"`: AWS physical host issue -> Proceed to Step 2.
  - If `InstanceStatus.Status == "impaired"`: Guest OS issue -> Proceed to Step 3.

### Step 2: System Status Check Remediation (Host Migration)
- **Why it matters:** Stopping an EBS-backed instance deallocates it from the faulty underlying physical host. Starting it forces AWS EC2 to allocate and launch it on a different, healthy physical server in the same Availability Zone.
- **Commands:**
  ```bash
  # Step A: Stop the instance
  aws ec2 stop-instances --instance-ids i-0123456789abcdef0

  # Step B: Wait for stopped state
  aws ec2 wait instance-stopped --instance-ids i-0123456789abcdef0

  # Step C: Start the instance
  aws ec2 start-instances --instance-ids i-0123456789abcdef0
  ```
- *Note:* Instance store volumes (ephemeral) are wiped upon instance stop. EBS volumes remain intact.

### Step 3: Instance Status Check Diagnostic (Retrieve System Log)
- **Why it matters:** The EC2 console output captures the Linux kernel boot log directly from the hypervisor serial console.
- **Command:**
  ```bash
  aws ec2 get-console-output \
    --instance-id i-0123456789abcdef0 \
    --output text
  ```
- **What to look for in output:**
  - `Kernel panic - not syncing: VFS: Unable to mount root fs`: Corrupt initramfs or missing kernel modules.
  - `Emergency mode`: File system check (`fsck`) failure or invalid mount entry in `/etc/fstab`.
  - `Out of memory: Kill process`: System ran completely out of RAM during boot.

## 5. Remediation for Guest OS Boot Failure
If console log shows `/etc/fstab` or corrupted filesystem:
1. Stop the impaired instance `i-0123456789abcdef0`.
2. Detach its root EBS volume (`/dev/xvda` or `/dev/sda1`).
3. Attach the volume to a healthy "rescue" EC2 instance in the same Availability Zone as `/dev/xvdf`.
4. Log into the rescue instance, mount the volume (`sudo mount /dev/xvdf1 /mnt`), and inspect:
   - Check and fix `/mnt/etc/fstab` (add `nofail` option to any non-root mount points).
   - Run `xfs_repair` or `e2fsck -f` on the unmounted partition if corrupt.
5. Unmount, detach from rescue instance, reattach to original instance as `/dev/xvda`, and start original instance.

## 6. Verification
Monitor instance status checks until both report `passed`:
```bash
aws ec2 describe-instance-status \
  --instance-ids i-0123456789abcdef0 \
  --query "InstanceStatuses[*].[InstanceId,SystemStatus.Status,InstanceStatus.Status]" \
  --output table
```
Expected output:
```text
------------------------------------------------------
|               DescribeInstanceStatus               |
+----------------------+---------+-------------------+
|  i-0123456789abcdef0 |  passed |  passed           |
+----------------------+---------+-------------------+
```

## 7. Prevention & Best Practices
1. **EC2 Auto-Recovery:** Create a CloudWatch Alarm on `StatusCheckFailed_System` with an EC2 recovery action (`arn:aws:automate:<region>:ec2:recover`). AWS will automatically migrate the instance to a healthy host without human intervention.
2. **Safe fstab syntax:** Always add `nofail` mount option to secondary volumes in `/etc/fstab` so missing EBS attachments don't halt instance boots.

## 8. Interview Discussion Points
- **Q: What is the difference between an EC2 instance reboot and a stop/start?**
  - *Answer:* A reboot restarts the guest operating system on the *same physical host*. A stop and start completely releases the physical host slot and launches the virtual machine on a *new physical host*, which resolves underlying hypervisor or hardware failures.
- **Q: What happens to IP addresses when an EC2 instance is stopped and started?**
  - *Answer:* The private IPv4 address remains unchanged. The ephemeral public IPv4 address is released back to the AWS pool unless the instance has an allocated Elastic IP (EIP) attached to it.

## 9. References
- [AWS EC2: Types of status checks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-system-instance-status-check.html)
- [AWS EC2: Recover your instance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-recover.html)
