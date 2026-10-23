# validate.ps1 — PowerShell validation script for CloudFirst Aid
param(
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " CloudFirst Aid - Local Validation Suite (PowerShell)" -ForegroundColor Cyan
Write-Host " Project Root: $projectRoot" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$env:PYTHONPATH = "src"

$pythonCmd = "python"
if (Test-Path ".venv\Scripts\python.exe") {
    $pythonCmd = ".venv\Scripts\python.exe"
}

# Step 1: Catalog Validation
Write-Host "`n[1/4] Validating Scenario Catalog..." -ForegroundColor Yellow
& $pythonCmd -m cloudfirst_aid.cli validate
if ($LASTEXITCODE -ne 0) {
    Write-Error "Scenario catalog validation failed."
}

# Step 2: Deterministic Triage Smoke Tests
Write-Host "`n[2/4] Testing Deterministic Triage Rules..." -ForegroundColor Yellow
$demos = @("CFA-001", "CFA-010", "CFA-011", "CFA-013", "CFA-017", "CFA-020")
foreach ($id in $demos) {
    Write-Host "  Testing $id..." -NoNewline
    & $pythonCmd -m cloudfirst_aid.cli triage $id | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Error "Triage execution failed for $id."
    }
    Write-Host " OK" -ForegroundColor Green
}

# Step 3: Run Automated Pytest Suite
Write-Host "`n[3/4] Running Automated Tests..." -ForegroundColor Yellow
& $pythonCmd -m pytest tests/unit -v --tb=short
if ($LASTEXITCODE -ne 0) {
    Write-Error "Automated test suite failed."
}

# Step 4: Secret and Credential Exposure Check
Write-Host "`n[4/4] Auditing for Secret Exposure..." -ForegroundColor Yellow
$secretHits = Get-ChildItem -Path @("scenarios", "runbooks", "src", "tests/fixtures") -Recurse -Include *.py,*.json,*.md | Select-String -Pattern "AKIA[0-9A-Z]{16}" -CaseSensitive
if ($secretHits) {
    Write-Error "Forbidden AWS access key pattern found in source files: $secretHits"
} else {
    Write-Host "  No live credentials or unredacted keys detected." -ForegroundColor Green
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " ALL VALIDATION CHECKS PASSED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
