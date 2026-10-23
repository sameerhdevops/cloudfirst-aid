# Runbook: High CPU, Memory Exhaustion, & OOM-Killer (CFA-012)

## 1. Problem
A critical service on an EC2 instance crashes without warning. The process manager reports exit code **137**. During the incident, the server became extremely unresponsive to SSH and web requests.

## 2. What the Engineer Sees
Checking service status:
```text
$ systemctl status backend-api.service
● backend-api.service - Production Backend API
   Loaded: loaded (/etc/systemd/system/backend-api.service; enabled)
   Active: failed (Result: signal) since Wed 2026-10-23 03:45:10 UTC; 10min ago
  Process: 18423 ExecStart=/usr/bin/node server.js (code=killed, signal=KILL)
```
Notice `signal=KILL` (SIGKILL / Signal 9). When combined with exit code 137 (`128 + 9 = 137`), this strongly indicates the **Linux Out-Of-Memory (OOM) Killer** terminated the process.

## 3. Before Changing Anything
1. **Never reboot the server immediately.** The kernel ring buffer (`dmesg`) holds the complete log of the OOM event, including memory stats, page cache consumption, and the process `oom_score`. Rebooting wipes standard `dmesg` buffers on non-persistent configurations.
2. Check if the instance has swap space configured. Most default AWS EC2 AMIs launch with **zero swap space**, meaning any memory spike immediately invokes the kernel OOM killer.

## 4. Investigation Sequence

### Step 1: Check Current Memory and Swap Utilization (Read-only Diagnostic)
- **Command:**
  ```bash
  free -h
  ```
- **Interpretation:**
  - Check the `available` column (not just `free`). In Linux, `free` memory is small because the kernel uses idle RAM for disk page caching. `available` indicates memory that can be given to applications without swapping.
  - If `Swap` total is `0B`, the system has no buffer against memory spikes.

### Step 2: Confirm OOM Killer Invocation in Kernel Ring Buffer (Read-only Diagnostic)
- **Command:**
  ```bash
  sudo dmesg -T | grep -iE "oom|out of memory|killed process" | tail -20
  ```
- **What to look for in output:**
  ```text
  [Fri Oct 23 03:45:09 2026] node invoked oom-killer: gfp_mask=0x1100cca(GFP_HIGHUSER_MOVABLE), order=0, oom_score_adj=0
  ...
  [Fri Oct 23 03:45:10 2026] Out of memory: Killed process 18423 (node) total-vm:4210452kB, anon-rss:1924100kB, file-rss:0kB, shmem-rss:0kB, UID:1000 pgtables:8204kB oom_score_adj:0
  ```
- **Distinguishing detail:** The kernel logs the exact process name, PID, and RSS (resident set size) at the time of termination.

### Step 3: Identify High CPU and Memory Consumers (Read-only Diagnostic)
- **Command:**
  ```bash
  # Top 10 memory-consuming processes:
  ps aux --sort=-%mem | head -n 11

  # Top 10 CPU-consuming processes:
  ps aux --sort=-%cpu | head -n 11
  ```
- **Look for:** Processes with high `%MEM` or `%CPU`, or runaway subprocesses spawned by Apache/PHP-FPM/Celery workers.

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| Application Memory Leak | **High** | Process RSS steadily grows over hours/days until OOM kill. |
| Inadequate Instance RAM Size (Undersized) | **High** | Instance has 1GB RAM (t3.micro), running multiple JVM/Node apps. |
| Zero Swap Space Configured | **Medium** | `free -h` shows Swap total = 0. |
| CPU Starvation / Infinite Loop | **Medium** | Process pinned at 100% CPU in `top`, load average exceeds vCPU count. |

## 6. Remediation

### Action A: Restart Service and Monitor Memory Growth (Local System Change)
```bash
sudo systemctl restart backend-api.service
```
Watch process memory in real time:
```bash
watch -n 2 'ps -eo pid,user,%cpu,%mem,rss,comm --sort=-rss | head -n 10'
```

### Action B: Configure Emergency Swap File (Local System Change)
For burst absorption while debugging the application:
```bash
# Allocate 2GB swap file:
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent in /etc/fstab:
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Action C: Set Systemd Memory Limits (Local System Change - Prevent Server-Wide Hangs)
Contain memory leaks to the specific service so the kernel doesn't kill other daemons (like SSH or database):
Edit `/etc/systemd/system/backend-api.service.d/override.conf`:
```ini
[Service]
MemoryMax=1.5G
MemoryHigh=1.2G
Restart=always
RestartSec=5s
```
Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart backend-api.service
```

### Action D: Resize EC2 Instance
If the workload genuinely requires more RAM:
1. Stop instance: `aws ec2 stop-instances --instance-ids i-xxxx`
2. Change instance type (e.g. from `t3.small` 2GB to `t3.medium` 4GB):
   ```bash
   aws ec2 modify-instance-attribute --instance-id i-xxxx --instance-type "{\"Value\": \"t3.medium\"}"
   ```
3. Start instance: `aws ec2 start-instances --instance-ids i-xxxx`

## 7. Verification
- `free -h` reports healthy available memory and active swap.
- Service remains in `active (running)` state over an extended observation period.
- No new OOM messages appear in `dmesg -T`.

## 8. Prevention & Best Practices
1. **Set CloudWatch Memory Alarms:** Configure the CloudWatch Agent to publish `mem_used_percent` and alert at 85%.
2. **Tune Application Runtimes:** Set Node.js `--max-old-space-size`, JVM `-Xmx` / `-Xms`, and PHP `memory_limit` to values lower than physical RAM.

## 9. Interview Discussion Points
- **Q: How does Linux choose which process to kill when out of memory?**
  - *Answer:* The Linux kernel calculates an `oom_score` for each process (from 0 to 1000) based on the percentage of total RAM it consumes, adjusted by `oom_score_adj` (-1000 to +1000). The process with the highest score is chosen to free the most memory with the least disruption. Privileged system daemons often have negative adjustment scores to protect them.
- **Q: Why does exit code 137 signify an OOM kill?**
  - *Answer:* Linux shells encode exit status for processes killed by signals as `128 + signal number`. Signal 9 is `SIGKILL` (`kill -9`), which is non-catchable and sent directly by the kernel OOM killer (`128 + 9 = 137`).

## 10. References
- `man 1 free`, `man 1 top`, `man 1 ps`, `man 5 proc`
- [AWS EC2: How do I allocate memory as swap space?](https://repost.aws/knowledge-center/ec2-memory-swap-file)
