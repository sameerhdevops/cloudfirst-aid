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
- Understand that in Linux (ext4/ext3), filesystems are formatted with a fixed number of **index nodes (inodes)**. Each inode stores file metadata (permissions, timestamps, block pointers).
- Every single file, directory, and symlink consumes exactly **one inode**, regardless of file size.
- 1,000,000 files of 0 bytes consume 0 bytes of block storage, but 1,000,000 inodes.
- Running standard tools like `ls` in a directory containing 1,000,000 files will hang or run out of memory. Always use `find` with `-delete` or `-exec rm`.

## 4. Investigation Sequence

### Step 1: Confirm Inode Usage by Filesystem
- **Command:**
  ```bash
  df -i
  ```
- **Interpretation:** Locate which partition has `IUse%: 100%` and `IFree: 0`.

### Step 2: Locate Directories with the Highest File Counts
- **Why it matters:** Pinpoint which specific directory tree contains the excessive file population.
- **Command:**
  ```bash
  sudo find / -xdev -printf '%h\n' 2>/dev/null | sort | uniq -c | sort -k1 -n | tail -15
  ```
- **Typical Output:**
  ```text
     1240 /usr/share/man
     2810 /var/lib/dpkg/info
  1285040 /var/spool/postfix/maildrop
  ```
- **Interpretation:** Directory `/var/spool/postfix/maildrop` contains 1.28 million files, consuming almost every available inode on the root volume.

### Step 3: Inspect the Nature of the Accumulated Files
- **Why it matters:** Determine what generated the files before deleting them.
- **Command:**
  ```bash
  sudo ls -f /var/spool/postfix/maildrop | head -n 10
  ```
- *Note:* Use `ls -f` (disables sorting), which returns results instantly instead of freezing while trying to sort a million files in memory.

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| Unchecked cron job email queue (`/var/spool/postfix` or `/var/spool/clientmqueue`) | **High** | Files accumulating in mail queue from local cron jobs outputting stdout/stderr without mail daemon configured. |
| PHP or application session files (`/var/lib/php/sessions`) | **High** | Hundreds of thousands of stale session files not purged by garbage collection. |
| Temporary file leak in `/tmp` | **Medium** | Microservices generating UUID temp files without cleanup handlers. |

## 6. Remediation

### Immediate Action: Clean the Offending Directory
Do NOT run `rm -rf /dir/*`—this fails with `-bash: /bin/rm: Argument list too long`.
Instead, use `find` with `-delete`:
```bash
# Example: delete files older than 7 days in the affected directory:
sudo find /var/spool/postfix/maildrop -type f -mtime +7 -delete

# Or to purge all accumulated queue files in emergencies:
sudo find /var/spool/postfix/maildrop -type f -delete
```

### Fix Cron Job Mail Flood
If cron jobs are dumping stdout to local maildrop:
Add `MAILTO=""` at the top of crontabs, or redirect output in individual jobs:
```crontab
* * * * * /usr/local/bin/myjob.sh > /dev/null 2>&1
```

### Fix PHP Session Cleanup
Ensure PHP session garbage collector cron is active:
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
- `man 1 df`, `man 1 find`, `man 5 tmpfiles.d`
- [AWS EC2: Troubleshooting disk space](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html)
