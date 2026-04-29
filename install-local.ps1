# LogSentinel Local Install Script (PowerShell)
# Installs the tool in editable/development mode

$ErrorActionPreference = "Stop"

Write-Host "Installing LogSentinel locally (editable mode)..." -ForegroundColor Cyan

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Change to the script directory
Set-Location $ScriptDir

# Uninstall first if exists (ignore errors)
Write-Host "Checking for existing installation..." -ForegroundColor Yellow
python -m pip uninstall logsentinel -y 2>$null | Out-Null

# Clean build and install from current source (editable mode)
python -m pip install --force-reinstall --no-cache-dir --no-build-isolation -e .

if ($LASTEXITCODE -eq 0) {
    Write-Host "LogSentinel installed successfully in editable mode!" -ForegroundColor Green
    Write-Host "You can now run 'logsentinel' from anywhere." -ForegroundColor Yellow
} else {
    Write-Host "Installation failed!" -ForegroundColor Red
    exit 1
}
