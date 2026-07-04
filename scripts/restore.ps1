param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDirectory,
    [switch]$IUnderstandThisOverwritesData
)

$ErrorActionPreference = "Stop"
if (-not $IUnderstandThisOverwritesData) {
    throw "Restore overwrites the current database and uploads. Re-run with -IUnderstandThisOverwritesData."
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackupRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "backups"))
$Source = (Resolve-Path -LiteralPath $BackupDirectory).Path
if (-not $Source.StartsWith($BackupRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw "Restore source must be a dated directory inside the workspace backups folder."
}

$ManifestPath = Join-Path $Source "backup.json"
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "backup.json is missing." }
$Manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
foreach ($Entry in $Manifest.files) {
    $FilePath = Join-Path $Source $Entry.name
    if (-not (Test-Path -LiteralPath $FilePath)) { throw "Missing backup file: $($Entry.name)" }
    $Actual = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Entry.sha256) { throw "Checksum failed for $($Entry.name). Restore cancelled." }
}

$DatabaseContainer = (docker compose ps -q postgres).Trim()
if (-not $DatabaseContainer) { throw "The postgres container must be running." }

Write-Host "Stopping the web application during restore..."
docker compose stop web | Out-Null
try {
    docker cp (Join-Path $Source "database.dump") "${DatabaseContainer}:/tmp/medivault-restore.dump" | Out-Null
    docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges /tmp/medivault-restore.dump'
    if ($LASTEXITCODE -ne 0) { throw "Database restore failed." }
    docker compose exec -T postgres rm -f /tmp/medivault-restore.dump

    Write-Host "Restoring uploaded documents..."
    docker compose run --rm --no-deps -v "${Source}:/restore:ro" --entrypoint sh web -c 'find /app/uploads -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xzf /restore/uploads.tar.gz -C /app/uploads'
    if ($LASTEXITCODE -ne 0) { throw "Upload restore failed." }
}
finally {
    docker compose start web | Out-Null
}

Write-Host "Restore completed. Verify with: Invoke-RestMethod http://localhost:8000/health/ready"
