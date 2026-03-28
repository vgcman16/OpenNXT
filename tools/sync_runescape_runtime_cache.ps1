param(
    [string]$SourceCacheDir = "",
    [string]$RuntimeCacheDir = "",
    [string]$SummaryOutput = "",
    [switch]$CheckOnly,
    [switch]$SeedMissingOnly,
    [int[]]$SkipJs5Archives = @(),
    [switch]$RescueSkippedBootstrapStubs,
    [switch]$ValidateSkippedArchives,
    [int]$BootstrapStubMaxLength = 12288,
    [switch]$NoOutput
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($SourceCacheDir)) {
    $SourceCacheDir = Join-Path $root "data\cache"
}
if ([string]::IsNullOrWhiteSpace($RuntimeCacheDir)) {
    if ([string]::IsNullOrWhiteSpace($env:ProgramData)) {
        throw "ProgramData is not available and -RuntimeCacheDir was not provided."
    }
    $RuntimeCacheDir = Join-Path $env:ProgramData "Jagex\RuneScape"
}

function Get-ArchiveIdFromFileName {
    param([string]$FileName)

    if ($FileName -match '^js5-(\d+)\.jcache$') {
        return [int]$Matches[1]
    }

    return $null
}

function Get-SharedSha256 {
    param([string]$Path)

    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "")
        } finally {
            $sha.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Get-SqliteCacheShape {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $null
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        return $null
    }

    $pythonScript = @'
import json
import sqlite3
import sys

path = sys.argv[1]
result = {"cache_rows": 0, "cache_index_rows": 0}
try:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cursor = connection.cursor()
    cache_rows = cursor.execute("select count(*) from cache").fetchone()
    cache_index_rows = cursor.execute("select count(*) from cache_index").fetchone()
    result["cache_rows"] = 0 if not cache_rows else int(cache_rows[0] or 0)
    result["cache_index_rows"] = 0 if not cache_index_rows else int(cache_index_rows[0] or 0)
    connection.close()
except Exception:
    pass

print(json.dumps(result))
'@

    try {
        $raw = & $pythonCommand.Source -c $pythonScript $Path 2>$null
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return $null
        }
        return $raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-MissingReferenceTableReason {
    param(
        [string]$SourcePath,
        [string]$RuntimePath
    )

    $sourceShape = Get-SqliteCacheShape -Path $SourcePath
    if ($null -eq $sourceShape -or $sourceShape.cache_index_rows -le 0) {
        return $null
    }

    $runtimeShape = Get-SqliteCacheShape -Path $RuntimePath
    if ($null -eq $runtimeShape -or $runtimeShape.cache_index_rows -le 0) {
        return "missing-reference-table"
    }

    return $null
}

if (-not (Test-Path $SourceCacheDir)) {
    throw "Source cache directory not found: $SourceCacheDir"
}

$sourceFiles = @(
    Get-ChildItem -Path $SourceCacheDir -Filter "js5-*.jcache" -File -ErrorAction Stop |
        Sort-Object Name
)
if ($sourceFiles.Count -eq 0) {
    throw "No js5-*.jcache files found in source cache directory: $SourceCacheDir"
}

if (-not (Test-Path $RuntimeCacheDir) -and -not $CheckOnly) {
    New-Item -ItemType Directory -Path $RuntimeCacheDir -Force | Out-Null
}

$entries = New-Object System.Collections.Generic.List[object]
$copiedArchives = New-Object System.Collections.Generic.List[int]
$plannedArchives = New-Object System.Collections.Generic.List[int]
$skippedArchives = New-Object System.Collections.Generic.List[int]
$rescuedArchives = New-Object System.Collections.Generic.List[int]
$validatedSkippedArchives = New-Object System.Collections.Generic.List[int]
$copiedBytes = [int64]0
$unchangedCount = 0
$effectiveValidateSkippedArchives = [bool]$ValidateSkippedArchives

foreach ($sourceFile in $sourceFiles) {
    $archiveId = Get-ArchiveIdFromFileName -FileName $sourceFile.Name
    if ($null -eq $archiveId) {
        continue
    }

    if ($SkipJs5Archives -contains $archiveId) {
        $runtimePath = Join-Path $RuntimeCacheDir $sourceFile.Name
        $runtimeLengthBefore = $null
        $runtimeWriteUtcBefore = $null
        $sourceHash = $null
        $runtimeHash = $null

        if (Test-Path $runtimePath) {
            $runtimeFile = Get-Item $runtimePath
            $runtimeLengthBefore = $runtimeFile.Length
            $runtimeWriteUtcBefore = $runtimeFile.LastWriteTimeUtc.ToString("o")
        }

        $shouldRescueSkippedArchive = $false
        $rescueReason = $null
        if ($RescueSkippedBootstrapStubs) {
            $runtimeLengthForRescue = if ($null -eq $runtimeLengthBefore) { -1 } else { [int64]$runtimeLengthBefore }
            if ($runtimeLengthForRescue -lt 0) {
                $shouldRescueSkippedArchive = $true
                $rescueReason = "rescue-skipped-missing-runtime"
            } elseif (
                $sourceFile.Length -gt $BootstrapStubMaxLength -and
                $runtimeLengthForRescue -le $BootstrapStubMaxLength -and
                $runtimeLengthForRescue -lt $sourceFile.Length
            ) {
                $shouldRescueSkippedArchive = $true
                $rescueReason = "rescue-skipped-bootstrap-stub"
            } elseif (
                $sourceFile.Length -le $BootstrapStubMaxLength -and
                $runtimeLengthForRescue -le $BootstrapStubMaxLength
            ) {
                $sourceHash = Get-SharedSha256 -Path $sourceFile.FullName
                $runtimeHash = Get-SharedSha256 -Path $runtimePath
                if ($sourceHash -ne $runtimeHash) {
                    $shouldRescueSkippedArchive = $true
                    $rescueReason = "rescue-skipped-bootstrap-hash-mismatch"
                }
            }
        }

        $shouldValidateSkippedArchive = $false
        $validateReason = $null
        if (-not $shouldRescueSkippedArchive -and $effectiveValidateSkippedArchives) {
            if (-not (Test-Path $runtimePath)) {
                $shouldValidateSkippedArchive = $true
                $validateReason = "validate-skipped-missing"
            } elseif ($runtimeLengthBefore -ne $sourceFile.Length) {
                $shouldValidateSkippedArchive = $true
                $validateReason = "validate-skipped-length-mismatch"
            } else {
                $referenceTableReason = Get-MissingReferenceTableReason -SourcePath $sourceFile.FullName -RuntimePath $runtimePath
                if ($null -ne $referenceTableReason) {
                    $shouldValidateSkippedArchive = $true
                    $validateReason = "validate-skipped-$referenceTableReason"
                } else {
                    $sourceHash = Get-SharedSha256 -Path $sourceFile.FullName
                    $runtimeHash = Get-SharedSha256 -Path $runtimePath
                    if ($sourceHash -ne $runtimeHash) {
                        $shouldValidateSkippedArchive = $true
                        $validateReason = "validate-skipped-hash-mismatch"
                    }
                }
            }
        }

        if ($shouldRescueSkippedArchive -or $shouldValidateSkippedArchive) {
            $plannedArchives.Add($archiveId) | Out-Null
            if ($shouldValidateSkippedArchive) {
                $validatedSkippedArchives.Add($archiveId) | Out-Null
            }
            if ($CheckOnly) {
                $action = if ($shouldRescueSkippedArchive) { "would-rescue-hot-stub" } else { "would-validate-skipped-copy" }
            } else {
                Copy-Item -Path $sourceFile.FullName -Destination $runtimePath -Force
                $action = if ($shouldRescueSkippedArchive) { "rescued-hot-stub" } else { "validated-skipped-copy" }
                $copiedArchives.Add($archiveId) | Out-Null
                if ($shouldRescueSkippedArchive) {
                    $rescuedArchives.Add($archiveId) | Out-Null
                }
                $copiedBytes += [int64]$sourceFile.Length
            }

            $entries.Add([pscustomobject]@{
                Archive = $archiveId
                SourcePath = $sourceFile.FullName
                RuntimePath = $runtimePath
                SourceLength = $sourceFile.Length
                RuntimeLengthBefore = $runtimeLengthBefore
                SourceWriteUtc = $sourceFile.LastWriteTimeUtc.ToString("o")
                RuntimeWriteUtcBefore = $runtimeWriteUtcBefore
                Action = $action
                Reason = if ($shouldRescueSkippedArchive) { $rescueReason } else { $validateReason }
                SourceSha256 = $sourceHash
                RuntimeSha256 = $runtimeHash
            }) | Out-Null
        } else {
            $skippedArchives.Add($archiveId) | Out-Null
            $entries.Add([pscustomobject]@{
                Archive = $archiveId
                SourcePath = $sourceFile.FullName
                RuntimePath = $runtimePath
                SourceLength = $sourceFile.Length
                RuntimeLengthBefore = $runtimeLengthBefore
                SourceWriteUtc = $sourceFile.LastWriteTimeUtc.ToString("o")
                RuntimeWriteUtcBefore = $runtimeWriteUtcBefore
                Action = "skipped"
                Reason = "skip-archive"
                SourceSha256 = $null
                RuntimeSha256 = $null
            }) | Out-Null
        }
        continue
    }

    $runtimePath = Join-Path $RuntimeCacheDir $sourceFile.Name
    $reason = $null
    $runtimeLengthBefore = $null
    $runtimeWriteUtcBefore = $null
    $sourceHash = $null
    $runtimeHash = $null
    $sourceWriteUtc = $sourceFile.LastWriteTimeUtc.ToString("o")

        if (-not (Test-Path $runtimePath)) {
            $reason = "missing"
        } else {
            $runtimeFile = Get-Item $runtimePath
            $runtimeLengthBefore = $runtimeFile.Length
            $runtimeWriteUtcBefore = $runtimeFile.LastWriteTimeUtc.ToString("o")

            if ($SeedMissingOnly) {
                $reason = $null
            } elseif ($runtimeFile.Length -ne $sourceFile.Length) {
                $reason = "length-mismatch"
            } else {
                $referenceTableReason = Get-MissingReferenceTableReason -SourcePath $sourceFile.FullName -RuntimePath $runtimePath
                if ($null -ne $referenceTableReason) {
                    $reason = $referenceTableReason
                } elseif ($runtimeFile.LastWriteTimeUtc -eq $sourceFile.LastWriteTimeUtc) {
                # The runtime copy is byte-for-byte identical to the staged cache when
                # both size and last-write timestamp already match. This avoids
                # rehashing multi-gigabyte .jcache files on every 947 launch.
                    $reason = $null
                } else {
                    $sourceHash = Get-SharedSha256 -Path $sourceFile.FullName
                    $runtimeHash = Get-SharedSha256 -Path $runtimePath
                    if ($sourceHash -ne $runtimeHash) {
                        $reason = "hash-mismatch"
                    }
                }
            }
    }

    $action = "unchanged"
    if ($null -ne $reason) {
        $plannedArchives.Add($archiveId) | Out-Null
        if ($CheckOnly) {
            $action = "would-copy"
        } else {
            Copy-Item -Path $sourceFile.FullName -Destination $runtimePath -Force
            $action = "copied"
            $copiedArchives.Add($archiveId) | Out-Null
            $copiedBytes += [int64]$sourceFile.Length
        }
    } else {
        $unchangedCount += 1
    }

    $entries.Add([pscustomobject]@{
        Archive = $archiveId
        SourcePath = $sourceFile.FullName
        RuntimePath = $runtimePath
        SourceLength = $sourceFile.Length
        RuntimeLengthBefore = $runtimeLengthBefore
        SourceWriteUtc = $sourceWriteUtc
        RuntimeWriteUtcBefore = $runtimeWriteUtcBefore
        Action = $action
        Reason = $reason
        SourceSha256 = $sourceHash
        RuntimeSha256 = $runtimeHash
    }) | Out-Null
}

$summary = [pscustomobject]@{
    SourceCacheDir = $SourceCacheDir
    RuntimeCacheDir = $RuntimeCacheDir
    CheckOnly = [bool]$CheckOnly
    SeedMissingOnly = [bool]$SeedMissingOnly
    RescueSkippedBootstrapStubs = [bool]$RescueSkippedBootstrapStubs
    ValidateSkippedArchives = $effectiveValidateSkippedArchives
    BootstrapStubMaxLength = $BootstrapStubMaxLength
    SkipJs5Archives = @($SkipJs5Archives)
    SourceFileCount = $sourceFiles.Count
    PlannedCopyCount = $plannedArchives.Count
    CopiedCount = $copiedArchives.Count
    RescuedCount = $rescuedArchives.Count
    ValidatedSkippedCount = $validatedSkippedArchives.Count
    SkippedCount = $skippedArchives.Count
    UnchangedCount = $unchangedCount
    CopiedBytes = $copiedBytes
    PlannedArchives = @($plannedArchives.ToArray())
    CopiedArchives = @($copiedArchives.ToArray())
    RescuedArchives = @($rescuedArchives.ToArray())
    ValidatedSkippedArchives = @($validatedSkippedArchives.ToArray())
    SkippedArchives = @($skippedArchives.ToArray())
    Entries = @($entries.ToArray())
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
