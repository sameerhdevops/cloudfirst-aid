# Incident Investigation Report: CFA-010

**Title:** Linux Root Filesystem 100% Full  
**Category:** Linux | **Severity:** CRITICAL | **Difficulty:** Beginner  
**Generated:** 2026-10-23 06:54:20 UTC  
**Investigating Agent / Operator:** CloudFirst Aid Diagnostic Engine  

---

## 1. Incident Overview

**Reported Symptom:**  
> Applications crash, services fail to write logs, and shell warns: 'No space left on device'.

**Initial Observations:**
- df -h shows / mounted on /dev/xvda1 is at 100% capacity (0 bytes available).
- Command line tab completion and temporary files fail.

**Target Environment / Prerequisites:**  
Amazon Linux 2 / Ubuntu EC2 instance.

## 2. Diagnostic Evidence & Provenance

> **Provenance Summary:** 3 Simulated Fixtures | 0 Local System Checks | 0 Live AWS Observations

### Evidence Item 1: `SIM-EVID-CFA010-01` (SIMULATED)
- **Description:** Filesystem block usage output (df -h)
- **Source Command / API:** `df -h`
- **Recorded At:** Fixture / Undated

```text
Filesystem      Size  Used Avail Use% Mounted on
devtmpfs        1.9G     0  1.9G   0% /dev
tmpfs           1.9G     0  1.9G   0% /dev/shm
tmpfs           1.9G  440K  1.9G   1% /run
/dev/xvda1       20G   20G     0 100% /
tmpfs           1.9G     0  1.9G   0% /sys/fs/cgroup
```

> **Known Limitation:** Simulated df -h output showing 100% capacity on the root partition.

### Evidence Item 2: `SIM-EVID-CFA010-02` (SIMULATED)
- **Description:** Top storage directory disk consumption (du -sh /var/*)
- **Source Command / API:** `sudo du -sh /var/* 2>/dev/null | sort -hr | head -n 5`
- **Recorded At:** Fixture / Undated

```text
16G	/var/log
1.2G	/var/lib
120M	/var/cache
4.0K	/var/tmp
4.0K	/var/spool
```

> **Known Limitation:** Shows /var/log consumes 16GB out of 20GB total volume capacity.

### Evidence Item 3: `SIM-EVID-CFA010-03` (SIMULATED)
- **Description:** Top storage-consuming files in /var/log
- **Source Command / API:** `sudo ls -lhS /var/log | head -n 5`
- **Recorded At:** Fixture / Undated

```text
total 16G
-rw-r--r-- 1 root root  14G Oct 23 04:12 app-transaction-debug.log
-rw-r--r-- 1 root root 1.8G Oct 23 04:12 syslog
-rw-r----- 1 root adm  180M Oct 23 03:00 messages
```

> **Known Limitation:** Isolates unrotated app-transaction-debug.log as the primary consumer.

## 3. Triage & Diagnostic Findings

Evaluation of evidence against deterministic troubleshooting rules:

### Finding 1: [CONFIRMED] Filesystem is at 100% capacity.
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA010-01
- **Diagnostic Explanation:** The df output shows a mounted filesystem at 100% usage. Applications writing to this mount point will receive 'No space left on device' errors.

### Finding 2: [POSSIBLE] Log directory may be consuming significant space.
- **Status:** `possible`
- **Supporting Evidence:** SIM-EVID-CFA010-02
- **Diagnostic Explanation:** The /var/log directory is a common source of disk exhaustion. Check for unrotated logs, verbose application logging, or repeated error messages filling log files.

## 4. Remediation Guidance

Recommended corrective actions based on candidate root causes:

### If Cause is: Unrotated or runaway log files in /var/log (Likelihood: common)
**Required Evidence to Confirm:** du -sh /var/log/* reveals single log file tens of gigabytes in size.

**Remediation Steps:**
Truncate runaway log file (`> /var/log/app.log`) and configure proper logrotate policy.

### If Cause is: Deleted large files still held open by a running process (Likelihood: occasional)
**Required Evidence to Confirm:** lsof +L1 shows unlinked files holding open file descriptors with non-zero size.

**Remediation Steps:**
Restart the process holding the file descriptor open or truncate via `/proc/$PID/fd/$FD`.

## 5. Verification & Prevention

**Verification Procedure:**  
Execute `df -h /` and verify Use% is below 80%.

**Prevention & Monitoring Best Practices:**
- Configure logrotate with size caps and compression.
- Set up CloudWatch disk metric alarms using CloudWatch agent.

## 6. Official References

- [https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html)

---
_Report compiled by CloudFirst Aid — offline-first AWS & Linux support diagnostic lab._
