# Incident Investigation Report: CFA-013

**Title:** systemd Service Fails to Start (CrashLoop)  
**Category:** Linux | **Severity:** HIGH | **Difficulty:** Intermediate  
**Generated:** 2026-10-23 06:54:20 UTC  
**Investigating Agent / Operator:** CloudFirst Aid Diagnostic Engine  

---

## 1. Incident Overview

**Reported Symptom:**  
> `systemctl start myapp` fails with 'Job for myapp.service failed because the control process exited with error code'.

**Initial Observations:**
- Service status shows Active: failed (Result: exit-code).
- Main PID exited with error code (status=1/FAILURE or status=127).

**Target Environment / Prerequisites:**  
Systemd managed Linux host.

## 2. Diagnostic Evidence & Provenance

> **Provenance Summary:** 3 Simulated Fixtures | 0 Local System Checks | 0 Live AWS Observations

### Evidence Item 1: `SIM-EVID-CFA013-01` (SIMULATED)
- **Description:** systemd unit status check (systemctl status)
- **Source Command / API:** `sudo systemctl status api-service.service --no-pager`
- **Recorded At:** Fixture / Undated

```text
● api-service.service - API Microservice Backend
     Loaded: loaded (/etc/systemd/system/api-service.service; enabled; vendor preset: enabled)
     Active: failed (Result: exit-code) since Wed 2026-10-23 04:15:22 UTC; 2min ago
    Process: 28412 ExecStart=/opt/api-service/bin/server (code=exited, status=1/FAILURE)
   Main PID: 28412 (code=exited, status=1/FAILURE)
```

> **Known Limitation:** Shows service failed with status=1.

### Evidence Item 2: `SIM-EVID-CFA013-02` (SIMULATED)
- **Description:** systemd journal error log (journalctl -u)
- **Source Command / API:** `sudo journalctl -u api-service.service -b --no-pager -n 10`
- **Recorded At:** Fixture / Undated

```text
Oct 23 04:15:22 ip-10-0-1-50 server[28412]: 2026/10/23 04:15:22 Starting HTTP listener on :8080
Oct 23 04:15:22 ip-10-0-1-50 server[28412]: 2026/10/23 04:15:22 listen tcp :8080: bind: Address already in use
Oct 23 04:15:22 ip-10-0-1-50 systemd[1]: api-service.service: Main process exited, code=exited, status=1/FAILURE
Oct 23 04:15:22 ip-10-0-1-50 systemd[1]: api-service.service: Failed with result 'exit-code'.
```

> **Known Limitation:** Explicitly captures 'bind: Address already in use' error.

### Evidence Item 3: `SIM-EVID-CFA013-03` (SIMULATED)
- **Description:** Listening socket inspection (ss -tlnp)
- **Source Command / API:** `sudo ss -tlnp 'sport = :8080'`
- **Recorded At:** Fixture / Undated

```text
State   Recv-Q  Send-Q   Local Address:Port   Peer Address:Port  Process
LISTEN  0       128            0.0.0.0:8080        0.0.0.0:*      users:(("old-api-daemon",pid=14201,fd=4))
```

> **Known Limitation:** Proves PID 14201 (old-api-daemon) already occupies port 8080.

## 3. Triage & Diagnostic Findings

Evaluation of evidence against deterministic troubleshooting rules:

### Finding 1: [CONFIRMED] Service is in failed state.
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA013-01
- **Diagnostic Explanation:** systemctl status shows the service has failed to start.

### Finding 2: [CONFIRMED] Service is in failed state.
- **Status:** `confirmed`
- **Supporting Evidence:** SIM-EVID-CFA013-02
- **Diagnostic Explanation:** systemctl status shows the service has failed to start.

### Finding 3: [SUPPORTED] Service cannot bind to its port — address already in use.
- **Status:** `supported`
- **Supporting Evidence:** SIM-EVID-CFA013-02
- **Diagnostic Explanation:** Another process is already listening on the port this service needs. Use 'ss -tlnp' or 'lsof -i :<port>' to identify it.

## 4. Remediation Guidance

Recommended corrective actions based on candidate root causes:

### If Cause is: Address already in use (another process already listening on the configured port) (Likelihood: common)
**Required Evidence to Confirm:** journalctl shows 'bind: Address already in use' or 'EADDRINUSE'.

**Remediation Steps:**
Identify conflicting process using `ss -tlnp` and stop it or adjust configuration port.

### If Cause is: Missing executable or wrong path specified in ExecStart directive (exit status 127) (Likelihood: common)
**Required Evidence to Confirm:** journalctl shows 'Failed at step EXEC spawning ...: No such file or directory'.

**Remediation Steps:**
Update ExecStart path in unit file to the absolute path of the verified binary, run daemon-reload.

## 5. Verification & Prevention

**Verification Procedure:**  
systemctl is-active myapp.service returns 'active'.

**Prevention & Monitoring Best Practices:**
- Validate configuration files before restarting systemd services.
- Use `systemctl daemon-reload` whenever unit files are edited.

## 6. Official References

- [https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html)

---
_Report compiled by CloudFirst Aid — offline-first AWS & Linux support diagnostic lab._
