param(
    [string]$OutputRoot = "",
    [int]$RetentionDays = 30,
    [string]$S3Bucket = "",
    [string]$AwsProfile = "medivault-backup"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputRoot) { $OutputRoot = Join-Path $ProjectRoot "backups" }
$BackupRoot = [IO.Path]::GetFullPath($OutputRoot)
if (-not $BackupRoot.StartsWith($ProjectRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw "Backup destination must remain inside the MedLog workspace."
}

$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$Destination = Join-Path $BackupRoot $Timestamp
New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$DatabaseContainer = (docker compose ps -q postgres).Trim()
$WebContainer = (docker compose ps -q web).Trim()
if (-not $DatabaseContainer -or -not $WebContainer) {
    throw "The postgres and web containers must be running before backup."
}

Write-Host "Creating a consistent PostgreSQL backup..."
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file=/tmp/medivault.dump'
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL backup failed." }
docker cp "${DatabaseContainer}:/tmp/medivault.dump" (Join-Path $Destination "database.dump") | Out-Null
docker compose exec -T postgres rm -f /tmp/medivault.dump

Write-Host "Archiving uploaded medical documents..."
docker compose exec -T web tar -czf /tmp/medivault-uploads.tar.gz -C /app/uploads .
if ($LASTEXITCODE -ne 0) { throw "Upload archive failed." }
docker cp "${WebContainer}:/tmp/medivault-uploads.tar.gz" (Join-Path $Destination "uploads.tar.gz") | Out-Null
docker compose exec -T web rm -f /tmp/medivault-uploads.tar.gz

$Files = @("database.dump", "uploads.tar.gz") | ForEach-Object {
    $Path = Join-Path $Destination $_
    [ordered]@{
        name = $_
        bytes = (Get-Item -LiteralPath $Path).Length
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
[ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    application = "MedLog"
    files = $Files
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $Destination "backup.json") -Encoding UTF8

if ($S3Bucket) {
    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        throw "AWS CLI is required when -S3Bucket is provided."
    }

    $S3Prefix = "medivault-backups/$Timestamp"
    $S3Uri = "s3://$S3Bucket/$S3Prefix/"
    Write-Host "Uploading the encrypted off-device copy to Amazon S3..."
    & aws s3 cp $Destination $S3Uri --recursive --sse AES256 --only-show-errors --profile $AwsProfile
    if ($LASTEXITCODE -ne 0) { throw "Amazon S3 backup upload failed. The local backup remains at $Destination" }

    @("database.dump", "uploads.tar.gz", "backup.json") | ForEach-Object {
        & aws s3api head-object --bucket $S3Bucket --key "$S3Prefix/$_" --profile $AwsProfile | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Amazon S3 verification failed for $_. The local backup remains at $Destination" }
    }
    Write-Host "Amazon S3 backup verified: $S3Uri"
}

if ($RetentionDays -gt 0) {
    $Cutoff = (Get-Date).ToUniversalTime().AddDays(-$RetentionDays)
    Get-ChildItem -LiteralPath $BackupRoot -Directory | Where-Object { $_.LastWriteTimeUtc -lt $Cutoff } | ForEach-Object {
        $Candidate = [IO.Path]::GetFullPath($_.FullName)
        if ($Candidate.StartsWith($BackupRoot + [IO.Path]::DirectorySeparatorChar)) {
            Remove-Item -LiteralPath $Candidate -Recurse -Force
        }
    }
}

Write-Host "Backup completed: $Destination"
if (-not $S3Bucket) {
    Write-Host "Keep an encrypted copy on a separate device or cloud backup location."
}
