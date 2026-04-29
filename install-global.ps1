# LogSentinel Global Install Script (PowerShell)
# Installs the tool by creating a .cmd launcher that calls the repo's logsentinel.py directly

$ErrorActionPreference = "Continue"

Write-Host "Installing LogSentinel globally..." -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "Step 1: Uninstall existing logsentinel..." -ForegroundColor Yellow
python -m pip uninstall logsentinel -y -q 2>$null | Out-Null

Write-Host "Step 2: Build wheel..." -ForegroundColor Yellow
$wheelDir = "$env:TEMP\ls_wheel_$PID"
New-Item -ItemType Directory -Path $wheelDir -Force | Out-Null
python -m pip wheel . --no-deps --wheel-dir $wheelDir 2>&1 | Out-Null

Write-Host "Step 3: Install to AppData..." -ForegroundColor Yellow
$targetScripts = "$env:APPDATA\Python\Python312\Scripts"
New-Item -ItemType Directory -Path $targetScripts -Force | Out-Null

python -m pip install "$wheelDir\logsentinel-1.0.0-py3-none-any.whl" --target $targetScripts --force-reinstall --no-deps 2>&1 | Out-Null

Write-Host "Step 4: Create .cmd launcher..." -ForegroundColor Yellow
# Create a .cmd launcher that invokes python on the local script
$cmdPath = "$targetScripts\logsentinel.cmd"
$lines = @(
    "@echo off",
    "python `"$ScriptDir\logsentinel.py`" %*"
)
[System.IO.File]::WriteAllLines($cmdPath, $lines)

Write-Host "Step 5: Verify..." -ForegroundColor Yellow
if (Test-Path $cmdPath) {
    Write-Host "SUCCESS! Installed at: $cmdPath" -ForegroundColor Green
    & cmd /c "$cmdPath --help" 2>&1 | Select-Object -First 15
} else {
    Write-Host "FAILED" -ForegroundColor Red
}

Write-Host "`nRun: logsentinel --monitor --namespace phoenix --level ERROR" -ForegroundColor Cyan