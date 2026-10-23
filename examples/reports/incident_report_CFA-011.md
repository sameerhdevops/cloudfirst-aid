# Incident Investigation Report: CFA-011

**Title:** Linux Inode Exhaustion (0 Inodes Available)  
**Category:** Linux | **Severity:** CRITICAL | **Difficulty:** Intermediate  
**Generated:** 2026-10-23 06:54:20 UTC  
**Investigating Agent / Operator:** CloudFirst Aid Diagnostic Engine  

---

## 1. Incident Overview

**Reported Symptom:**  
> Application encounters 'No space left on device', but `df -h` shows gigabytes of free disk capacity.

**Initial Observations:**
- df -h reports 40% disk space free.
- touch /tmp/testfile fails with 'No space left on device'.

**Target Environment / Prerequisites:**  
Linux server hosting web service with extensive temporary or session files.

## 2. Diagnostic Evidence & Provenance

> **Provenance Summary:** 2 Simulated Fixtures | 0 Local System Checks | 0 Live AWS Observations

### Evidence Item 1: `SIM-EVID-CFA011-01` (SIMULATED)
- **Description:** Inode allocation check across filesystems (df -i)
- **Source Command / API:** `df -i`
- **Recorded At:** Fixture / Undated

```text
Filesystem      Inodes   IUsed   IFree IUse% Mounted on
devtmpfs        486214     342  485872    1% /dev
tmpfs           488210       1  488209    1% /dev/shm
tmpfs           488210     412  487798    1% /run
/dev/xvda1     1310720 1310720       0  100% /
tmpfs           488210       1  488209    1% /sys/fs/cgroup
```

> **Known Limitation:** Shows root partition has exhausted 100% of its 1,310,720 available inodes.

### Evidence Item 2: `SIM-EVID-CFA011-02` (SIMULATED)
- **Description:** Top directory file counts (find | uniq -c)
- **Source Command / API:** `sudo find /var/spool/postfix/maildrop -type f | wc -l`
- **Recorded At:** Fixture / Undated

```text
1198420 /var/spool/postfix/maildrop
```

> **Known Limitation:** Confirms over 1.1 million small orphan maildrop queue files.

## 3. Triage & Diagnostic Findings

Evaluation of evidence against deterministic troubleshooting rules:

### Finding 1: [CONFIRMED] Inodes are 100% exhausted on a filesystem.
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA011-01
- **Diagnostic Explanation:** The filesystem has consumed all available index nodes (inodes). Operating system cannot create new file entries or directory nodes even if free disk capacity remains.

### Finding 2: [CONFIRMED] Over 1 million orphan files identified in queue/cache directory.
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA011-02
- **Diagnostic Explanation:** Large accumulations of small files (such as an undelivered mail queue or stale PHP session store) are the primary root cause of inode exhaustion.

## 4. Remediation Guidance

Recommended corrective actions based on candidate root causes:

### If Cause is: Millions of tiny session or temporary files accumulated in /tmp, /var/spool, or /var/lib/php/sessions (Likelihood: common)
**Required Evidence to Confirm:** df -i shows IUse% at 100%; directory contains hundreds of thousands of entries.

**Remediation Steps:**
Clean accumulated orphan session files using find with -delete, and configure cron cleanup job.

## 5. Verification & Prevention

**Verification Procedure:**  
Run `df -i /` and confirm IFree > 0 and IUse% < 80%.

**Prevention & Monitoring Best Practices:**
- Set up automated tmpfiles.d or cron cleanup policies for session caches.
- Monitor inode usage alongside disk block usage in CloudWatch.

## 6. Official References

- [https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html)

---
_Report compiled by CloudFirst Aid — offline-first AWS & Linux support diagnostic lab._
