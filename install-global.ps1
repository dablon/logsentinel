# LogSentinel Global Install Script (PowerShell)
# Installs the tool system-wide

$ErrorActionPreference = "Stop"

Write-Host "Installing LogSentinel globally..." -ForegroundColor Cyan

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Change to the script directory
Set-Location $ScriptDir

# Uninstall first if exists (ignore errors)
Write-Host "Checking for existing installation..." -ForegroundColor Yellow
python -m pip uninstall logsentinel -y 2>$null | Out-Null

# Install globally with --user to avoid Windows permission issues
python -m pip install --user --force-reinstall --no-deps .

if ($LASTEXITCODE -eq 0) {
    Write-Host "LogSentinel installed successfully globally!" -ForegroundColor Green
    Write-Host "IMPORTANT: Add this to your PATH:" -ForegroundColor Yellow
    Write-Host "  `$env:PATH += `";`$env:APPDATA\Python\Python312\Scripts`"" -ForegroundColor Cyan
    Write-Host "Or run: `$env:PATH += `";`$env:APPDATA\Python\Python312\Scripts`"" -ForegroundColor Cyan
} else {
    Write-Host "Installation failed!" -ForegroundColor Red
    exit 1
}
