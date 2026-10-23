# Runbook: Linux Inode Exhaustion (CFA-011)

## 1. Problem
A system administrator or developer reports:
> "Our application is crashing with 'No space left on device'. But when I run `df -h`, it shows 15GB of free disk space available! What is going on?"

## 2. What the Engineer Sees
Checking disk space (`df -h`):
```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/xvda1       20G  5.2G   15G  26% /
```
Yet creating any file fails immediately:
```bash
$ touch /tmp/testfile
touch: cannot touch '/tmp/testfile': No space left on device
```

Checking inode allocation (`df -i`):
```text
Filesystem      Inodes   IUsed   IFree IUse% Mounted on
/dev/xvda1     1310720 1310720       0  100% /
```
The filesystem has **0 free inodes** (`IFree: 0`, `IUse%: 100%`).

## 3. Before Changing Anything
- Understand that in Linux filesystems like ext4, the volume is formatted with a fixed number of **index nodes (inodes)**. Each inode stores file metadata (permissions, timestamps, file size, block pointers).
- Every file, directory, named pipe, and symlink consumes exactly **one inode**, regardless of file size.
- A million 0-byte files consume 0 bytes of block storage, but 1,000,000 inodes.
- Running standard commands like `ls` or `rm *` in a directory containing hundreds of thousands of files will freeze or fail with `Argument list too long` because the shell attempts to buffer and sort all directory entries in memory.
- Deletions are irreversible. Never execute broad deletion commands without first previewing candidate files and verifying what process produced them.

## 4. Investigation Sequence

### Step 1: Check Inode Allocation Across All Filesystems (Read-only Diagnostic)
- **Command:**
  ```bash
  df -i
  ```
- **Interpretation:** Identify which filesystem has exhausted its inode table (`IUse%: 100%` and `IFree: 0`). Note the filesystem device name and mount point.

### Step 2: Compare Inode Usage Against Block Capacity (Read-only Diagnostic)
- **Command:**
  ```bash
  df -h
  ```
- **Interpretation:** Contrast `Use%` (block storage) with `IUse%` (inode count). If block usage is low (e.g. 25%) while inode usage is 100%, the problem is definitively driven by a massive population of very small or 0-byte files, not large files or database bloat.

### Step 3: Isolate the Specific Filesystem Mount Point
- **Why it matters:** Filesystem operations must not span across other mounted volumes, network shares (NFS), or virtual filesystems (`/proc`, `/sys`).
- **Interpretation:** Ensure subsequent search commands use the `-xdev` (or `-mount`) flag to constrain traversal strictly to the affected filesystem.

### Step 4: Locate High-Count Directory Hierarchies (Read-only Diagnostic)
- **Why it matters:** Pinpoint which specific directory tree contains the excessive file population.
- **Command:**
  ```bash
  sudo find / -xdev -printf '%h\n' 2>/dev/null | sort | uniq -c | sort -k1 -n | tail -15
  ```
  *(Replace `/` with the affected mount point if not root.)*
- **Typical Output:**
  ```text
     1240 /usr/share/man
     2810 /var/lib/dpkg/info
  1285040 /var/spool/postfix/maildrop
  ```
- **Interpretation:** Directory `/var/spool/postfix/maildrop` contains 1.28 million files, consuming almost every available inode on the root volume.

### Step 5: Safely Drill Down into Candidate Directories Without Memory Hangs (Read-only Diagnostic)
- **Why it matters:** Running standard `ls` in a directory with 1.2 million files attempts to sort all filenames in memory, causing the shell to hang or trigger an OOM kill.
- **Command:**
  ```bash
  sudo ls -f /var/spool/postfix/maildrop | head -n 20
  ```
- **Interpretation:** The `-f` flag disables sorting and directory buffering, outputting file entries in raw directory order immediately without memory overhead.

### Step 6: Analyze File Names, Timestamps, and Ownership (Read-only Diagnostic)
- **Why it matters:** Determine which subsystem, process, or user created the files before taking any destructive action.
- **Commands:**
  ```bash
  # Inspect file timestamps and attributes of sample files:
  sudo stat /var/spool/postfix/maildrop/$(sudo ls -f /var/spool/postfix/maildrop | sed -n '3p')
  ```
- **Interpretation:** Note the creation/modification rate, owner UID/GID, and file naming pattern. If thousands of files share identical minute-by-minute timestamps, an unthrottled cron job or looping script is actively running.

### Step 7: Check for Active Processes Writing or Holding Deleted Files (Read-only Diagnostic)
- **Why it matters:** If an application is actively writing files or holding unlinked open files, deleting them will not free space until the process closes the file descriptors.
- **Commands:**
  ```bash
  # Check for active processes holding unlinked files on the filesystem:
  sudo lsof +L1 /
  
  # Check which process currently has open handles in the target directory:
  sudo fuser -v /var/spool/postfix/maildrop/
  ```
- **Interpretation:** Identify the daemon or service (e.g., `postfix`, `crond`, `php-fpm`, or a custom daemon) before stopping or cleaning up.

### Step 8: Formulate a Cautious, Scoped Remediation Plan (Preview First)
- **Why it matters:** Deleting system files carries operational risks. Never run unconstrained blanket deletions.
- **Consequences of Indiscriminate Deletion by Category:**
  - **Mail Spool (`/var/spool/postfix` or `/var/spool/clientmqueue`):** Permanently discards queued messages and system error notifications. Before deleting, verify whether the spool contains legitimate application emails or an endless bounce loop caused by an unconfigured MTA.
  - **PHP / Web Sessions (`/var/lib/php/sessions`):** Deleting active session files forcefully logs out active end-users and discards uncommitted shopping carts or state. Only delete session files older than the session timeout (e.g., `-mtime +2`).
  - **Temporary Directories (`/tmp`, `/var/tmp`):** Deleting active UNIX domain sockets or locks breaks inter-process communication for running daemons. Use time-scoped filters (`-atime`, `-mtime`) or `systemd-tmpfiles --clean`.
- **Safe Preview Commands (MANDATORY before deletion):**
  ```bash
  # Preview candidate files older than 7 days:
  sudo find /var/spool/postfix/maildrop -type f -mtime +7 -print | head -n 25
  ```

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| Unchecked cron job email queue (`/var/spool/postfix` or `/var/spool/clientmqueue`) | **High** | Files accumulating in mail queue from local cron jobs outputting stdout/stderr without mail daemon configured. |
| PHP or application session files (`/var/lib/php/sessions`) | **High** | Hundreds of thousands of stale session files not purged by garbage collection. |
| Temporary file leak in `/tmp` | **Medium** | Microservices generating UUID temp files without cleanup handlers. |

## 6. Remediation

### Safety Rule: Always Preview Target Files Before Deletion
**CAUTION:** `find ... -delete` is unprompted, immediate, and irreversible. Running it against the wrong path or pattern will permanently destroy data. Always run a non-destructive preview first to inspect candidate files.

### Action A: Clean Target Directory with Time-Scoped Filtering (Local System Change)
Do NOT run `rm -rf /dir/*`—this fails with `-bash: /bin/rm: Argument list too long`.
Instead, preview first, then delete strictly filtered matching files:

```bash
# 1. Preview candidate files older than 7 days:
sudo find /var/spool/postfix/maildrop -type f -mtime +7 -print | head -n 20

# 2. After verifying preview results, delete only files older than 7 days:
sudo find /var/spool/postfix/maildrop -type f -mtime +7 -delete

# 3. For sessions, target only files exceeding session expiration TTL:
sudo find /var/lib/php/sessions -type f -cmin +1440 -delete
```

### Action B: Fix Root Cause in Cron or Application (Local System Change)
If cron jobs are dumping stdout to local maildrop:
Add `MAILTO=""` at the top of crontabs, or redirect output in individual jobs:
```crontab
* * * * * /usr/local/bin/myjob.sh > /dev/null 2>&1
```

### Action C: Fix Session Garbage Collection (Local System Change)
Ensure PHP session garbage collector timer is active:
```bash
sudo systemctl status php-session-cleanup.timer
```

## 7. Verification
Run `df -i /` to confirm available inodes:
```bash
df -i /
```
Expected output:
```text
Filesystem      Inodes   IUsed   IFree IUse% Mounted on
/dev/xvda1     1310720  145020 1165700   12% /
```
Test creating a file:
```bash
touch /tmp/testfile && rm /tmp/testfile
# Succeeds without error
```

## 8. Prevention & Best Practices
1. **Monitor Inodes in CloudWatch:** In the CloudWatch Agent JSON config, include `diskio` and `disk` metric `inodes_free` or `inodes_used_percent`.
2. **Configure systemd-tmpfiles:** Create cleanup rules in `/etc/tmpfiles.d/` for application cache directories.

## 9. Interview Discussion Points
- **Q: Can you increase the number of inodes on an existing ext4 filesystem?**
  - *Answer:* No. In ext4 filesystems, the number of inodes is determined at format time (`mkfs.ext4 -N <inodes>`) and is stored in static tables. To increase inodes, you must back up data, reformat the volume with a higher inode density, or switch to XFS (which dynamically allocates inodes as needed up to a configurable maximum).

## 10. References
- `man 1 df`, `man 1 find`, `man 1 lsof`, `man 1 fuser`, `man 5 tmpfiles.d`
- [AWS EC2: Troubleshooting disk space](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html)
