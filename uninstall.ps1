# LogSentinel Uninstall Script (PowerShell)

$ErrorActionPreference = "Stop"

Write-Host "Uninstalling LogSentinel..." -ForegroundColor Cyan

python -m pip uninstall logsentinel -y
python -m pip uninstall logsentinel -y --user 2>$null | Out-Null

if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 0) {
    Write-Host "LogSentinel uninstalled successfully!" -ForegroundColor Green
} else {
    Write-Host "Uninstall failed or package was not installed!" -ForegroundColor Yellow
    exit 1
}
