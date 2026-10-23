#!/usr/bin/env bash
#
# validate.sh — Bash validation script for CloudFirst Aid
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

echo "=========================================================="
echo " CloudFirst Aid — Local Validation Suite (Bash)"
echo " Project Root: ${PROJECT_ROOT}"
echo "=========================================================="

export PYTHONPATH="src"

# Step 1: Validate Catalog
echo ""
echo "[1/4] Validating Scenario Catalog..."
python3 -m cloudfirst_aid.cli validate

# Step 2: Test Triage Demos
echo ""
echo "[2/4] Testing Deterministic Triage Rules..."
DEMOS=("CFA-001" "CFA-010" "CFA-011" "CFA-013" "CFA-017" "CFA-020")
for id in "${DEMOS[@]}"; do
    printf "  Testing %s... " "$id"
    python3 -m cloudfirst_aid.cli triage "$id" >/dev/null
    echo "OK"
done

# Step 3: Run Pytest
echo ""
echo "[3/4] Running Automated Tests..."
python3 -m pytest tests/unit -v --tb=short

# Step 4: Secret Audit
echo ""
echo "[4/4] Auditing for Secret Exposure..."
if grep -rE "AKIA[0-9A-Z]{16}" scenarios/ runbooks/ src/ tests/fixtures/ 2>/dev/null; then
    echo "ERROR: Unredacted AWS Access Key ID detected!"
    exit 1
else
    echo "  No live credentials or unredacted keys detected."
fi

echo ""
echo "=========================================================="
echo " ALL VALIDATION CHECKS PASSED SUCCESSFULLY!"
echo "=========================================================="
