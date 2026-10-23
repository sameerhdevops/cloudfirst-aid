# Runbook: Linux Root Filesystem 100% Full (CFA-010)

## 1. Problem
Applications crash across the server, background workers exit unexpectedly, and database writes abort. An engineer attempting to run shell commands receives:
```text
-bash: cannot create temp file for here-document: No space left on device
```

## 2. What the Engineer Sees
Running `df -h`:
```text
Filesystem      Size  Used Avail Use% Mounted on
devtmpfs        1.9G     0  1.9G   0% /dev
tmpfs           1.9G     0  1.9G   0% /dev/shm
tmpfs           1.9G  440K  1.9G   1% /run
/dev/xvda1       20G   20G     0 100% /
tmpfs           1.9G     0  1.9G   0% /sys/fs/cgroup
```
The root filesystem `/` on `/dev/xvda1` has **0 bytes available**.

## 3. Before Changing Anything
1. **Do not run `rm -rf` impulsively.** Deleting system directories or arbitrary files can render the system unbootable.
2. **Beware of deleted open files:** Running `rm` on a file while a process still has an open file descriptor does **not** free disk space on Linux. The storage remains allocated until the process closes the file handle or is restarted.
3. **Forensic Integrity Warning — Preserving Diagnostic History:** Truncating or zeroing active logs (`truncate -s 0 /var/log/app.log`) immediately destroys recent diagnostic history, making post-mortem analysis impossible. Before truncating, preserve recent error entries:
   ```bash
   # Save the last 1,000 lines if possible before zeroing:
   tail -n 1000 /var/log/app-debug.log > /tmp/preserved_tail.log
   ```
4. **Truncate vs Delete:** Use file truncation (`truncate -s 0 file.log` or `: > file.log`) instead of `rm file.log` for active logs to immediately release space without stranding open unlinked file descriptors.

## 4. Investigation Sequence

### Step 1: Confirm Filesystem Capacity and Mount Point (Read-only Diagnostic)
- **Command:**
  ```bash
  df -h
  ```
- **Interpretation:** Identify which mount point is at 100%. If it is `/var` on a separate partition, only services logging to `/var` will fail; if `/` is full, core OS operations fail.

### Step 2: Identify Top Consuming Directories (Read-only Diagnostic)
- **Why it matters:** Recursively isolate which directory contains the accumulated data.
- **Command:**
  ```bash
  sudo du -h --max-depth=1 / 2>/dev/null | sort -hr | head -n 10
  ```
- **Typical Output:**
  ```text
  16G    /var
  2.4G   /usr
  800M   /home
  ```
- **Next check:** Drill into the top directory (e.g. `sudo du -h --max-depth=1 /var 2>/dev/null | sort -hr`).

### Step 3: Check /var/log for Runaway Unrotated Log Files (Read-only Diagnostic)
- **Why it matters:** Runaway logs in `/var/log` are the most frequent cause of storage exhaustion on application servers.
- **Command:**
  ```bash
  sudo ls -lhS /var/log | head -n 10
  ```
- **What to look for:** Single log files exceeding multiple gigabytes (e.g. `app-debug.log`, `syslog`, `nginx/access.log`).

### Step 4: Detect Deleted Files Still Held Open by Processes (Read-only Diagnostic)
- **Why it matters:** If `df -h` reports 100% used, but `du -sh /*` only accounts for 8GB, a running process is holding open deleted files.
- **Command:**
  ```bash
  sudo lsof / | grep -i deleted | sort -k7 -nr | head -n 10
  ```
- **What to look for:** Lines showing `(deleted)` with large file sizes and active PID/daemon names (e.g., `java`, `nginx`, `rsyslogd`).

## 5. Remediation

### Immediate Action A: Safely Truncate Runaway Log Files (Local System Change)
After preserving a diagnostic sample of recent errors, truncate the file to 0 bytes:
```bash
# Safely zero the file content without changing inode or file descriptor:
sudo truncate -s 0 /var/log/app-debug.log
# OR via shell redirection:
sudo sh -c ': > /var/log/app-debug.log'
```

### Immediate Action B: Release Deleted Open Files (Local System Change)
If `lsof` revealed deleted open files, restart the process holding the descriptor:
```bash
sudo systemctl restart <process-name>
```
*Emergency method without restarting process:* Truncate the descriptor directly via `/proc`:
```bash
sudo sh -c ': > /proc/<PID>/fd/<FD_NUMBER>'
```

### Immediate Action C: Clean Systemd Journal Logs (Local System Change)
If systemd journal is consuming space:
```bash
sudo journalctl --vacuum-size=200M
```

## 6. Verification
Run `df -h /` to confirm available storage:
```bash
df -h /
```
Expected output:
```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/xvda1       20G  4.2G   16G  21% /
```

## 7. Prevention & Best Practices
1. **Configure logrotate properly:** Ensure `/etc/logrotate.d/` contains active rotation rules with `maxsize`, `rotate 7`, and `compress`.
2. **Install and configure CloudWatch Agent:** Emit `disk_used_percent` metrics to CloudWatch and set an alarm at 80% capacity to trigger alerts before an outage occurs.
3. **Dedicated partitions:** Mount `/var/log` on a separate EBS volume so runaway logs cannot crash the root filesystem.

## 8. Interview Discussion Points
- **Q: Why does `df` show 100% full even after running `rm` on a huge 10GB log file?**
  - *Answer:* In Linux, a file's data blocks are only freed when its link count is zero AND all open file descriptors referencing its inode are closed. If an active process has the file open, `rm` unlinks the directory entry, but the process continues writing to the open inode. The space remains consumed until the process terminates or closes the file descriptor.
- **Q: How does `truncate -s 0 file.log` differ from `rm file.log`?**
  - *Answer:* `truncate` immediately shrinks the file length to zero without removing the directory entry or altering the inode number. Any active process with an open file descriptor can immediately continue writing without restarting.

## 9. References
- `man 1 df`, `man 1 du`, `man 8 lsof`, `man 8 logrotate`
- [AWS EC2: Troubleshoot storage space issues](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html)
