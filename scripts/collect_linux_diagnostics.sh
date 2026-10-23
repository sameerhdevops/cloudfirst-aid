#!/usr/bin/env bash
#
# collect_linux_diagnostics.sh
# Non-destructive local Linux system diagnostic collector for CloudFirst Aid.
#
# INVARIANTS:
# - Completely safe and non-destructive (read-only commands).
# - NEVER collects or outputs secrets, passwords, or credentials.
# - NEVER alters system configuration, services, or files.
# - Suitable for local troubleshooting practice and evidence gathering.

set -euo pipefail

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
HOSTNAME=$(hostname -s 2>/dev/null || echo "localhost")

echo "================================================================="
echo " CloudFirst Aid — Linux System Diagnostic Snapshot"
echo " Timestamp: ${TIMESTAMP} | Host: ${HOSTNAME}"
echo "================================================================="
echo ""

echo "--- [1/6] Operating System & Kernel ---"
uname -srm
if [ -f /etc/os-release ]; then
    grep -E '^(PRETTY_NAME|ID|VERSION)=' /etc/os-release || true
fi
echo ""

echo "--- [2/6] Filesystem Disk Capacity (df -h) ---"
df -h -x tmpfs -x devtmpfs -x squashfs 2>/dev/null || df -h
echo ""

echo "--- [3/6] Filesystem Inode Allocation (df -i) ---"
df -i -x tmpfs -x devtmpfs -x squashfs 2>/dev/null || df -i
echo ""

echo "--- [4/6] Memory & Swap Overview (free -h) ---"
free -h 2>/dev/null || cat /proc/meminfo | head -n 5
echo ""

echo "--- [5/6] Top 5 Memory-Consuming Processes ---"
ps -eo pid,user,%cpu,%mem,rss,comm --sort=-rss 2>/dev/null | head -n 6 || true
echo ""

echo "--- [6/6] Listening Network Ports (ss -tlnp) ---"
if command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null || ss -tln 2>/dev/null || true
elif command -v netstat >/dev/null 2>&1; then
    netstat -tlnp 2>/dev/null || netstat -tln 2>/dev/null || true
else
    echo "Notice: ss/netstat utilities not installed."
fi
echo ""

echo "================================================================="
echo " Diagnostic collection completed successfully."
echo "================================================================="
