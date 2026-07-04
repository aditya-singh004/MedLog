$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

Write-Host "MedLog containers"
docker compose ps

Write-Host "`nApplication checks"
try {
    $Live = Invoke-RestMethod -Uri "http://localhost:8000/health/live" -TimeoutSec 5
    $Ready = Invoke-RestMethod -Uri "http://localhost:8000/health/ready" -TimeoutSec 5
    Write-Host "Liveness: $($Live.status)"
    Write-Host "Readiness: $($Ready.status); database: $($Ready.database)"
}
catch {
    Write-Warning "Health check failed: $($_.Exception.Message)"
}

$BackupRoot = Join-Path $ProjectRoot "backups"
$Latest = Get-ChildItem -LiteralPath $BackupRoot -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if ($Latest) {
    $Age = [math]::Round(((Get-Date).ToUniversalTime() - $Latest.LastWriteTimeUtc).TotalHours, 1)
    Write-Host "Latest backup: $($Latest.Name) ($Age hours old)"
    if ($Age -gt 26) { Write-Warning "The latest backup is more than 26 hours old." }
}
else {
    Write-Warning "No local backups found. Run .\scripts\backup.ps1"
}
