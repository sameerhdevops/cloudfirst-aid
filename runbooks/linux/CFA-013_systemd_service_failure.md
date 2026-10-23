# Runbook: systemd Service Fails to Start / CrashLoop (CFA-013)

## 1. Problem
A system administrator or CI/CD deployment script runs `sudo systemctl start api-gateway.service`, and the command immediately aborts with:
```text
Job for api-gateway.service failed because the control process exited with error code.
See "systemctl status api-gateway.service" and "journalctl -xeu api-gateway.service" for details.
```

## 2. What the Engineer Sees
Running `systemctl status api-gateway.service`:
```text
● api-gateway.service - API Gateway Service
     Loaded: loaded (/etc/systemd/system/api-gateway.service; enabled; vendor preset: enabled)
     Active: failed (Result: exit-code) since Wed 2026-10-23 04:12:05 UTC; 1min ago
    Process: 24891 ExecStart=/usr/local/bin/api-gateway --config /etc/api-gateway.yaml (code=exited, status=1/FAILURE)
   Main PID: 24891 (code=exited, status=1/FAILURE)
```
The service is in `failed` state and exited immediately upon launch.

## 3. Before Changing Anything
1. **Always read the journal logs first:** Never blindly edit service unit files or guess configuration parameters. Systemd captures both stdout and stderr of the daemon before it terminates.
2. Note the **status code**:
   - `status=1/FAILURE`: Application started, encountered an error (bad config, missing DB, port conflict), and cleanly called `exit(1)`.
   - `status=127`: Executable not found (`ExecStart` path incorrect).
   - `status=126`: File exists but is not executable (`chmod +x` missing).
   - `status=203/EXEC`: Failed to set user/group or change directory (`User=` does not exist or working directory missing).

## 4. Investigation Sequence

### Step 1: Inspect Detailed Journal Logs
- **Command:**
  ```bash
  sudo journalctl -u api-gateway.service -b --no-pager -n 50
  ```
- **What to look for in output:**
  ```text
  Oct 23 04:12:05 ip-10-0-1-50 api-gateway[24891]: [INFO] Loading configuration from /etc/api-gateway.yaml
  Oct 23 04:12:05 ip-10-0-1-50 api-gateway[24891]: [ERROR] listen tcp 0.0.0.0:8080: bind: Address already in use
  Oct 23 04:12:05 ip-10-0-1-50 systemd[1]: api-gateway.service: Main process exited, code=exited, status=1/FAILURE
  ```
- **Interpretation:** The failure is caused by an **Address already in use** (port conflict on 8080).

### Step 2: Identify Conflicting Process on the Port
- **Command:**
  ```bash
  sudo ss -tlnp 'sport = :8080'
  ```
- **Output:**
  ```text
  State   Recv-Q  Send-Q   Local Address:Port   Peer Address:Port  Process
  LISTEN  0       128            0.0.0.0:8080        0.0.0.0:*      users:(("old-gateway",pid=12044,fd=3))
  ```
- **Interpretation:** PID 12044 (`old-gateway`) is already bound to port 8080.

### Step 3: Inspect Service Unit File Syntax and Permissions
- **Command:**
  ```bash
  systemctl cat api-gateway.service
  ```
- **Check:**
  - Does the binary in `ExecStart` exist and have execute permissions (`ls -l /usr/local/bin/api-gateway`)?
  - Does the user specified in `User=` exist in `/etc/passwd`?
  - Does the path in `WorkingDirectory=` exist and is it readable by the service user?

## 5. Possible Causes & Likelihood
| Cause | Likelihood | Distinguishing Evidence |
|---|---|---|
| Port Conflict (`bind: Address already in use`) | **High** | Journal log shows `EADDRINUSE` or `bind: Address already in use`. |
| Bad Configuration File / Syntax Error | **High** | Journal shows YAML/JSON parse error or invalid setting. |
| File / Directory Permission Denied | **Medium** | Journal shows `EACCES` or `Permission denied` on log/pid path. |
| Missing Binary or Bad Path | **Low** | Status code `127` or `Failed at step EXEC spawning`. |

## 6. Remediation

### If Port Conflict (Old Process Running):
Terminate the rogue process:
```bash
sudo kill -15 12044
# Verify port is released:
sudo ss -tlnp 'sport = :8080'
# Start the systemd service:
sudo systemctl start api-gateway.service
```

### If Unit File Edited:
Whenever you modify a unit file in `/etc/systemd/system/`:
```bash
sudo systemctl daemon-reload
sudo systemctl restart api-gateway.service
```

### If Failed State is Stuck:
Clear the failed counter if systemd refuses further start attempts:
```bash
sudo systemctl reset-failed api-gateway.service
sudo systemctl start api-gateway.service
```

## 7. Verification
Run `systemctl status`:
```bash
systemctl status api-gateway.service
```
Expected output:
```text
● api-gateway.service - API Gateway Service
     Loaded: loaded (/etc/systemd/system/api-gateway.service; enabled)
     Active: active (running) since Wed 2026-10-23 04:18:22 UTC; 15s ago
   Main PID: 25112 (api-gateway)
      Tasks: 6 (limit: 4627)
     Memory: 24.5M
```

## 8. Prevention & Best Practices
1. **Configure graceful restarts in deployment automation:** Always issue `systemctl stop old-service` before starting new instances.
2. **Add restart policies:** Include `Restart=on-failure` and `RestartSec=5s` in the `[Service]` section to recover automatically from transient failures.

## 9. Interview Discussion Points
- **Q: Why does `systemctl daemon-reload` exist?**
  - *Answer:* When systemd boots, it compiles and caches unit file definitions into memory. If you edit a `.service` file on disk, systemd continues using the cached configuration in memory until you run `systemctl daemon-reload`, which re-parses all unit files on disk.
- **Q: What is the difference between `systemctl stop` and `systemctl kill`?**
  - *Answer:* `systemctl stop` sends the configured stop command or `SIGTERM` to the main process and waits for clean shutdown. `systemctl kill` sends a direct signal (default `SIGTERM`) to all processes in the service's cgroup without executing `ExecStop` commands.

## 10. References
- `man 1 systemctl`, `man 1 journalctl`, `man 5 systemd.service`
- [AWS EC2: Troubleshoot operating system issues](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting.html)
