param(
    [string]$RuntimeCacheDir = "",
    [int[]]$ArchiveIds = @(2,3,8,12,13,16,17,18,19,20,21,22,24,26,27,28,29,49,57,58,59,60,61,62,65,66),
    [switch]$IncludeAuxiliaryFiles,
    [string]$BackupRoot = "",
    [string]$Tag = "",
    [string]$SummaryOutput = "",
    [switch]$NoOutput
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($RuntimeCacheDir)) {
    if ([string]::IsNullOrWhiteSpace($env:ProgramData)) {
        throw "ProgramData is not available and -RuntimeCacheDir was not provided."
    }
    $RuntimeCacheDir = Join-Path $env:ProgramData "Jagex\RuneScape"
}

if (-not (Test-Path $RuntimeCacheDir)) {
    throw "Runtime cache directory not found: $RuntimeCacheDir"
}

if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = Get-Date -Format "yyyyMMdd-HHmmss"
}

if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
    $BackupRoot = Join-Path $root ("data\debug\runtime-hot-cache-backups\{0}" -f $Tag)
}

if (-not (Test-Path $BackupRoot)) {
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
}

$requestedNames = New-Object System.Collections.Generic.List[string]
foreach ($archiveId in ($ArchiveIds | Select-Object -Unique | Sort-Object)) {
    $requestedNames.Add(("js5-{0}.jcache" -f $archiveId)) | Out-Null
}
if ($IncludeAuxiliaryFiles) {
    foreach ($name in @("ObjCache.jcache", "GlobalSettings.jcache", "ShaderManager.jcache")) {
        $requestedNames.Add($name) | Out-Null
    }
}

$moved = New-Object System.Collections.Generic.List[object]
$missing = New-Object System.Collections.Generic.List[string]

foreach ($name in ($requestedNames | Select-Object -Unique)) {
    $sourcePath = Join-Path $RuntimeCacheDir $name
    if (-not (Test-Path $sourcePath)) {
        $missing.Add($name) | Out-Null
        continue
    }

    $destinationPath = Join-Path $BackupRoot $name
    Move-Item -Path $sourcePath -Destination $destinationPath -Force
    $movedFile = Get-Item $destinationPath
    $moved.Add([pscustomobject]@{
        Name = $name
        BackupPath = $destinationPath
        Length = $movedFile.Length
        LastWriteTimeUtc = $movedFile.LastWriteTimeUtc.ToString("o")
    }) | Out-Null
}

$summary = [pscustomobject]@{
    RuntimeCacheDir = $RuntimeCacheDir
    BackupRoot = $BackupRoot
    Tag = $Tag
    IncludeAuxiliaryFiles = [bool]$IncludeAuxiliaryFiles
    RequestedNames = @($requestedNames.ToArray())
    RequestedCount = $requestedNames.Count
    MovedCount = $moved.Count
    MissingCount = $missing.Count
    MovedFiles = @($moved.ToArray())
    MissingFiles = @($missing.ToArray())
}

$json = $summary | ConvertTo-Json -Depth 6
if (-not [string]::IsNullOrWhiteSpace($SummaryOutput)) {
    $summaryDirectory = Split-Path -Parent $SummaryOutput
    if (-not [string]::IsNullOrWhiteSpace($summaryDirectory) -and -not (Test-Path $summaryDirectory)) {
        New-Item -ItemType Directory -Path $summaryDirectory -Force | Out-Null
    }
    Set-Content -Path $SummaryOutput -Value $json -Encoding UTF8
}

if (-not $NoOutput) {
    Write-Output $json
}
