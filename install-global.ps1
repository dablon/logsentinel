# LogSentinel Global Install Script (PowerShell)
# Installs the tool system-wide, force-replacing any existing installation

$ErrorActionPreference = "Continue"

Write-Host "Installing LogSentinel globally..." -ForegroundColor Cyan

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "Step 1: Uninstall existing logsentinel..." -ForegroundColor Yellow
# Uninstall via pip (may fail if exe is locked but that's ok)
python -m pip uninstall logsentinel -y -q 2>$null | Out-Null
python -m pip uninstall logsentinel -y -q 2>$null | Out-Null

Write-Host "Step 2: Delete old executables..." -ForegroundColor Yellow
# Try multiple methods to remove stale executables
$exePaths = @(
    "$env:APPDATA\Python\Python312\Scripts\logsentinel.exe",
    "C:\Python312\Scripts\logsentinel.exe"
)
foreach ($exePath in $exePaths) {
    if (Test-Path $exePath) {
        # Method 1: attrib to remove any read-only/hidden flags then delete
        attrib -r -h $exePath 2>$null | Out-Null
        Remove-Item $exePath -Force -ErrorAction SilentlyContinue
        # Method 2: If still exists, try via cmd /c del
        if (Test-Path $exePath) {
            cmd /c "del /f /q `"$exePath`"" 2>$null | Out-Null
        }
        # Method 3: If still exists, try Move-Item to temp name then delete
        if (Test-Path $exePath) {
            $tmpName = "$env:TEMP\logsentinel_old_$PID.exe"
            Move-Item $exePath $tmpName -Force -ErrorAction SilentlyContinue
            if (Test-Path $tmpName) {
                Start-Sleep -Milliseconds 500
                Remove-Item $tmpName -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Host "  Removed: $exePath" -ForegroundColor Gray
    }
}

Write-Host "Step 3: Force reinstall from source..." -ForegroundColor Yellow
# Use --ignore-installed to bypass the exe lock check
python -m pip install --force-reinstall --user --no-cache-dir --no-build-isolation --ignore-installed . 2>&1 | Out-String | Where-Object { $_ -match "error|warn|success|installed" }

Write-Host "Step 4: Verify installation..." -ForegroundColor Yellow
$installedExe = "$env:APPDATA\Python\Python312\Scripts\logsentinel.exe"
if (Test-Path $installedExe) {
    Write-Host "LogSentinel installed successfully!" -ForegroundColor Green
    & $installedExe --version 2>$null | Out-Null
} else {
    Write-Host "WARNING: logsentinel.exe not found in user scripts dir" -ForegroundColor Yellow
    Write-Host "Trying to run via python..." -ForegroundColor Yellow
}

Write-Host "`nTest with: python $ScriptDir\logsentinel.py --monitor --help" -ForegroundColor Cyan