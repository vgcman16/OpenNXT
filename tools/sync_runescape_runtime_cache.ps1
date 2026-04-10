param(
    [string]$SourceCacheDir = "",
    [string]$RuntimeCacheDir = "",
    [string]$SummaryOutput = "",
    [switch]$CheckOnly,
    [switch]$SeedMissingOnly,
    [switch]$SeedCorePrefixedAliases,
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

function Get-RuntimeArchiveTargetNames {
    param(
        [int]$ArchiveId,
        [switch]$IncludeCorePrefixedAliases
    )

    $targetNames = New-Object System.Collections.Generic.List[string]
    $targetNames.Add(("js5-{0}.jcache" -f $ArchiveId)) | Out-Null
    if ($IncludeCorePrefixedAliases) {
        $targetNames.Add(("core-js5-{0}.jcache" -f $ArchiveId)) | Out-Null
    }

    return @($targetNames.ToArray())
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
        $raw = $pythonScript | & $pythonCommand.Source - $Path 2>$null
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

function Get-RuntimeTargetState {
    param([string]$RuntimePath)

    if (-not (Test-Path $RuntimePath)) {
        return [pscustomobject]@{
            Exists = $false
            RuntimeLengthBefore = $null
            RuntimeWriteUtcBefore = $null
        }
    }

    $runtimeFile = Get-Item -LiteralPath $RuntimePath -ErrorAction Stop
    return [pscustomobject]@{
        Exists = $true
        RuntimeLengthBefore = $runtimeFile.Length
        RuntimeWriteUtcBefore = $runtimeFile.LastWriteTimeUtc.ToString("o")
    }
}

function Get-TargetSyncDecision {
    param(
        [System.IO.FileInfo]$SourceFile,
        [string]$RuntimePath,
        [switch]$SeedMissingOnly
    )

    $targetState = Get-RuntimeTargetState -RuntimePath $RuntimePath
    $reason = $null
    $sourceHash = $null
    $runtimeHash = $null

    if (-not $targetState.Exists) {
        $reason = "missing"
    } elseif ($SeedMissingOnly) {
        $reason = $null
    } elseif ($targetState.RuntimeLengthBefore -ne $SourceFile.Length) {
        $reason = "length-mismatch"
    } else {
        $referenceTableReason = Get-MissingReferenceTableReason -SourcePath $SourceFile.FullName -RuntimePath $RuntimePath
        if ($null -ne $referenceTableReason) {
            $reason = $referenceTableReason
        } else {
            $runtimeFile = Get-Item -LiteralPath $RuntimePath -ErrorAction Stop
            if ($runtimeFile.LastWriteTimeUtc -ne $SourceFile.LastWriteTimeUtc) {
                $sourceHash = Get-SharedSha256 -Path $SourceFile.FullName
                $runtimeHash = Get-SharedSha256 -Path $RuntimePath
                if ($sourceHash -ne $runtimeHash) {
                    $reason = "hash-mismatch"
                }
            }
        }
    }

    return [pscustomobject]@{
        RuntimePath = $RuntimePath
        Exists = $targetState.Exists
        RuntimeLengthBefore = $targetState.RuntimeLengthBefore
        RuntimeWriteUtcBefore = $targetState.RuntimeWriteUtcBefore
        Reason = $reason
        SourceSha256 = $sourceHash
        RuntimeSha256 = $runtimeHash
    }
}

function Get-SkippedArchiveRescueDecisions {
    param(
        [System.IO.FileInfo]$SourceFile,
        [string[]]$RuntimePaths,
        [int]$BootstrapStubMaxLength
    )

    $decisions = New-Object System.Collections.Generic.List[object]
    foreach ($runtimePath in $RuntimePaths) {
        $targetState = Get-RuntimeTargetState -RuntimePath $runtimePath
        $reason = $null
        $sourceHash = $null
        $runtimeHash = $null

        if (-not $targetState.Exists) {
            $reason = "rescue-skipped-missing-runtime"
        } elseif (
            $SourceFile.Length -gt $BootstrapStubMaxLength -and
            $targetState.RuntimeLengthBefore -le $BootstrapStubMaxLength -and
            $targetState.RuntimeLengthBefore -lt $SourceFile.Length
        ) {
            $reason = "rescue-skipped-bootstrap-stub"
        } elseif (
            $SourceFile.Length -le $BootstrapStubMaxLength -and
            $targetState.RuntimeLengthBefore -le $BootstrapStubMaxLength
        ) {
            $sourceHash = Get-SharedSha256 -Path $SourceFile.FullName
            $runtimeHash = Get-SharedSha256 -Path $runtimePath
            if ($sourceHash -ne $runtimeHash) {
                $reason = "rescue-skipped-bootstrap-hash-mismatch"
            }
        }

        if ($null -ne $reason) {
            $decisions.Add([pscustomobject]@{
                RuntimePath = $runtimePath
                Exists = $targetState.Exists
                RuntimeLengthBefore = $targetState.RuntimeLengthBefore
                RuntimeWriteUtcBefore = $targetState.RuntimeWriteUtcBefore
                Reason = $reason
                SourceSha256 = $sourceHash
                RuntimeSha256 = $runtimeHash
            }) | Out-Null
        }
    }

    return @($decisions.ToArray())
}

function Get-SkippedArchiveValidationDecisions {
    param(
        [System.IO.FileInfo]$SourceFile,
        [string[]]$RuntimePaths
    )

    $decisions = New-Object System.Collections.Generic.List[object]
    foreach ($runtimePath in $RuntimePaths) {
        $targetDecision = Get-TargetSyncDecision -SourceFile $SourceFile -RuntimePath $runtimePath
        if ($null -eq $targetDecision.Reason) {
            continue
        }

        $mappedReason = switch ($targetDecision.Reason) {
            "missing" { "validate-skipped-missing" }
            "length-mismatch" { "validate-skipped-length-mismatch" }
            "missing-reference-table" { "validate-skipped-missing-reference-table" }
            "hash-mismatch" { "validate-skipped-hash-mismatch" }
            default { "validate-skipped-$($targetDecision.Reason)" }
        }

        $decisions.Add([pscustomobject]@{
            RuntimePath = $runtimePath
            Exists = $targetDecision.Exists
            RuntimeLengthBefore = $targetDecision.RuntimeLengthBefore
            RuntimeWriteUtcBefore = $targetDecision.RuntimeWriteUtcBefore
            Reason = $mappedReason
            SourceSha256 = $targetDecision.SourceSha256
            RuntimeSha256 = $targetDecision.RuntimeSha256
        }) | Out-Null
    }

    return @($decisions.ToArray())
}

function Get-CopyFailureReason {
    param(
        [Parameter(Mandatory = $true)]
        [System.Management.Automation.ErrorRecord]$ErrorRecord
    )

    $message = [string]$ErrorRecord.Exception.Message
    if ($message -match 'being used by another process') {
        return "copy-failed-locked"
    }

    return "copy-failed"
}

function Try-CopyRuntimeArchive {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$RuntimePath
    )

    try {
        Copy-Item -Path $SourcePath -Destination $RuntimePath -Force
        return [pscustomobject]@{
            Success = $true
            Reason = $null
            ErrorMessage = $null
        }
    } catch {
        return [pscustomobject]@{
            Success = $false
            Reason = Get-CopyFailureReason -ErrorRecord $_
            ErrorMessage = [string]$_.Exception.Message
        }
    }
}

function Test-IsCoreAliasTargetPath {
    param([string]$RuntimePath)

    $name = Split-Path -Leaf $RuntimePath
    return $name -like "core-js5-*.jcache"
}

function Get-CoreAliasPrimaryRuntimePath {
    param([string]$AliasRuntimePath)

    if (-not (Test-IsCoreAliasTargetPath -RuntimePath $AliasRuntimePath)) {
        return $null
    }

    $aliasName = Split-Path -Leaf $AliasRuntimePath
    $primaryName = $aliasName -replace '^core-', ''
    return Join-Path (Split-Path -Parent $AliasRuntimePath) $primaryName
}

function Try-ReplaceRuntimeAliasWithHardLink {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PrimaryRuntimePath,
        [Parameter(Mandatory = $true)]
        [string]$AliasRuntimePath
    )

    try {
        if (-not (Test-Path $PrimaryRuntimePath)) {
            throw "Primary runtime archive does not exist: $PrimaryRuntimePath"
        }

        if (Test-Path $AliasRuntimePath) {
            Remove-Item -LiteralPath $AliasRuntimePath -Force
        }

        New-Item -ItemType HardLink -Path $AliasRuntimePath -Target $PrimaryRuntimePath -Force | Out-Null
        return [pscustomobject]@{
            Success = $true
            Reason = "hardlinked-alias"
            ErrorMessage = $null
        }
    } catch {
        return [pscustomobject]@{
            Success = $false
            Reason = "hardlink-failed"
            ErrorMessage = [string]$_.Exception.Message
        }
    }
}

function Repair-ExistingCoreAliasHardLinks {
    param([string]$RuntimeCacheDir)

    $results = New-Object System.Collections.Generic.List[object]
    $aliasPaths = @(
        Get-ChildItem -LiteralPath $RuntimeCacheDir -Filter "core-js5-*.jcache" -File -ErrorAction SilentlyContinue |
            Sort-Object Name |
            Select-Object -ExpandProperty FullName
    )

    foreach ($aliasPath in $aliasPaths) {
        $primaryPath = Get-CoreAliasPrimaryRuntimePath -AliasRuntimePath $aliasPath
        if ([string]::IsNullOrWhiteSpace($primaryPath) -or -not (Test-Path -LiteralPath $primaryPath) -or -not (Test-Path -LiteralPath $aliasPath)) {
            continue
        }

        $primaryFile = Get-Item -LiteralPath $primaryPath -ErrorAction SilentlyContinue
        $aliasFile = Get-Item -LiteralPath $aliasPath -ErrorAction SilentlyContinue
        if ($null -eq $primaryFile -or $null -eq $aliasFile) {
            continue
        }

        if ($primaryFile.Length -ne $aliasFile.Length) {
            continue
        }

        $repairResult = Try-ReplaceRuntimeAliasWithHardLink -PrimaryRuntimePath $primaryPath -AliasRuntimePath $aliasPath
        $results.Add([pscustomobject]@{
            AliasRuntimePath = $aliasPath
            PrimaryRuntimePath = $primaryPath
            AliasLengthBefore = [int64]$aliasFile.Length
            Success = [bool]$repairResult.Success
            Reason = $repairResult.Reason
            ErrorMessage = $repairResult.ErrorMessage
        }) | Out-Null
    }

    return @($results.ToArray())
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
$plannedTargetCount = 0
$copiedTargetCount = 0
$failedTargetCount = 0
$unchangedTargetCount = 0
$skippedTargetCount = 0
$effectiveValidateSkippedArchives = [bool]$ValidateSkippedArchives
$failedArchives = New-Object System.Collections.Generic.List[int]
$copyErrors = New-Object System.Collections.Generic.List[object]
$repairedExistingCoreAliasCount = 0
$repairedExistingCoreAliasBytes = [int64]0
$repairedExistingCoreAliasErrors = New-Object System.Collections.Generic.List[object]

if ($SeedCorePrefixedAliases -and -not $CheckOnly -and (Test-Path -LiteralPath $RuntimeCacheDir)) {
    $existingAliasRepairs = @(Repair-ExistingCoreAliasHardLinks -RuntimeCacheDir $RuntimeCacheDir)
    foreach ($existingAliasRepair in $existingAliasRepairs) {
        if ($existingAliasRepair.Success) {
            $repairedExistingCoreAliasCount += 1
            $repairedExistingCoreAliasBytes += [int64]$existingAliasRepair.AliasLengthBefore
        } else {
            $repairedExistingCoreAliasErrors.Add([pscustomobject]@{
                AliasRuntimePath = $existingAliasRepair.AliasRuntimePath
                PrimaryRuntimePath = $existingAliasRepair.PrimaryRuntimePath
                ErrorMessage = $existingAliasRepair.ErrorMessage
            }) | Out-Null
        }
    }
}

foreach ($sourceFile in $sourceFiles) {
    $archiveId = Get-ArchiveIdFromFileName -FileName $sourceFile.Name
    if ($null -eq $archiveId) {
        continue
    }

    $runtimeTargetNames = @(Get-RuntimeArchiveTargetNames -ArchiveId $archiveId -IncludeCorePrefixedAliases:$SeedCorePrefixedAliases)
    $runtimeTargetPaths = @($runtimeTargetNames | ForEach-Object { Join-Path $RuntimeCacheDir $_ })
    $sourceWriteUtc = $sourceFile.LastWriteTimeUtc.ToString("o")

    if ($SkipJs5Archives -contains $archiveId) {
        $targetDecisions = @()
        $archiveAction = "skipped"
        $copyResultsByPath = @{}

        if ($RescueSkippedBootstrapStubs) {
            $targetDecisions = @(Get-SkippedArchiveRescueDecisions -SourceFile $sourceFile -RuntimePaths $runtimeTargetPaths -BootstrapStubMaxLength $BootstrapStubMaxLength)
        }

        if ($targetDecisions.Count -gt 0) {
            $plannedArchives.Add($archiveId) | Out-Null
            $plannedTargetCount += $targetDecisions.Count
            if ($CheckOnly) {
                $archiveAction = "would-rescue-hot-stub"
            } else {
                $hadCopyFailure = $false
                foreach ($targetDecision in $targetDecisions) {
                    $copyResult = Try-CopyRuntimeArchive -SourcePath $sourceFile.FullName -RuntimePath $targetDecision.RuntimePath
                    $copyResultsByPath[$targetDecision.RuntimePath] = $copyResult
                    if ($copyResult.Success) {
                        $copiedBytes += [int64]$sourceFile.Length
                        $copiedTargetCount += 1
                    } else {
                        $hadCopyFailure = $true
                        $failedTargetCount += 1
                        $copyErrors.Add([pscustomobject]@{
                            Archive = $archiveId
                            SourcePath = $sourceFile.FullName
                            RuntimePath = $targetDecision.RuntimePath
                            Reason = $copyResult.Reason
                            ErrorMessage = $copyResult.ErrorMessage
                        }) | Out-Null
                    }
                }
                if ($hadCopyFailure) {
                    $failedArchives.Add($archiveId) | Out-Null
                    $archiveAction = "copy-failed"
                } else {
                    $copiedArchives.Add($archiveId) | Out-Null
                    $rescuedArchives.Add($archiveId) | Out-Null
                    $archiveAction = "rescued-hot-stub"
                }
            }
        } elseif ($effectiveValidateSkippedArchives) {
            $targetDecisions = @(Get-SkippedArchiveValidationDecisions -SourceFile $sourceFile -RuntimePaths $runtimeTargetPaths)
            if ($targetDecisions.Count -gt 0) {
                $plannedArchives.Add($archiveId) | Out-Null
                $validatedSkippedArchives.Add($archiveId) | Out-Null
                $plannedTargetCount += $targetDecisions.Count
                if ($CheckOnly) {
                    $archiveAction = "would-validate-skipped-copy"
                } else {
                    $hadCopyFailure = $false
                    foreach ($targetDecision in $targetDecisions) {
                        $copyResult = Try-CopyRuntimeArchive -SourcePath $sourceFile.FullName -RuntimePath $targetDecision.RuntimePath
                        $copyResultsByPath[$targetDecision.RuntimePath] = $copyResult
                        if ($copyResult.Success) {
                            $copiedBytes += [int64]$sourceFile.Length
                            $copiedTargetCount += 1
                        } else {
                            $hadCopyFailure = $true
                            $failedTargetCount += 1
                            $copyErrors.Add([pscustomobject]@{
                                Archive = $archiveId
                                SourcePath = $sourceFile.FullName
                                RuntimePath = $targetDecision.RuntimePath
                                Reason = $copyResult.Reason
                                ErrorMessage = $copyResult.ErrorMessage
                            }) | Out-Null
                        }
                    }
                    if ($hadCopyFailure) {
                        $failedArchives.Add($archiveId) | Out-Null
                        $archiveAction = "copy-failed"
                    } else {
                        $copiedArchives.Add($archiveId) | Out-Null
                        $archiveAction = "validated-skipped-copy"
                    }
                }
            }
        }

        if ($targetDecisions.Count -eq 0) {
            $skippedArchives.Add($archiveId) | Out-Null
        }

        foreach ($runtimeTargetPath in $runtimeTargetPaths) {
            $targetDecision = $targetDecisions | Where-Object { $_.RuntimePath -eq $runtimeTargetPath } | Select-Object -First 1
            if ($null -ne $targetDecision) {
                $targetAction = if ($CheckOnly) {
                    if ($archiveAction -eq "would-rescue-hot-stub") { "would-rescue-hot-stub" } else { "would-validate-skipped-copy" }
                } else {
                    $copyResult = $copyResultsByPath[$runtimeTargetPath]
                    if ($copyResult -and -not $copyResult.Success) {
                        $copyResult.Reason
                    } elseif ($archiveAction -eq "rescued-hot-stub") {
                        "rescued-hot-stub"
                    } elseif ($archiveAction -eq "validated-skipped-copy") {
                        "validated-skipped-copy"
                    } else {
                        "copy-failed"
                    }
                }
            } else {
                $targetState = Get-RuntimeTargetState -RuntimePath $runtimeTargetPath
                $targetDecision = [pscustomobject]@{
                    RuntimePath = $runtimeTargetPath
                    Exists = $targetState.Exists
                    RuntimeLengthBefore = $targetState.RuntimeLengthBefore
                    RuntimeWriteUtcBefore = $targetState.RuntimeWriteUtcBefore
                    Reason = "skip-archive"
                    SourceSha256 = $null
                    RuntimeSha256 = $null
                }
                $targetAction = "skipped"
                $skippedTargetCount += 1
            }

            $entries.Add([pscustomobject]@{
                Archive = $archiveId
                SourcePath = $sourceFile.FullName
                RuntimePath = $runtimeTargetPath
                RuntimeTargetPaths = @($runtimeTargetPaths)
                RuntimeTargetName = Split-Path -Leaf $runtimeTargetPath
                SourceLength = $sourceFile.Length
                RuntimeLengthBefore = $targetDecision.RuntimeLengthBefore
                SourceWriteUtc = $sourceWriteUtc
                RuntimeWriteUtcBefore = $targetDecision.RuntimeWriteUtcBefore
                Action = $targetAction
                ArchiveAction = $archiveAction
                Reason = if (-not $CheckOnly -and $copyResultsByPath.ContainsKey($runtimeTargetPath) -and -not $copyResultsByPath[$runtimeTargetPath].Success) {
                    $copyResultsByPath[$runtimeTargetPath].Reason
                } else {
                    $targetDecision.Reason
                }
                SourceSha256 = $targetDecision.SourceSha256
                RuntimeSha256 = $targetDecision.RuntimeSha256
            }) | Out-Null
        }

        continue
    }

    $primaryRuntimePath = $runtimeTargetPaths[0]
    $targetDecisions = @(
        foreach ($runtimeTargetPath in $runtimeTargetPaths) {
            $targetDecision = Get-TargetSyncDecision -SourceFile $sourceFile -RuntimePath $runtimeTargetPath -SeedMissingOnly:$SeedMissingOnly
            $isCoreAliasTarget = $SeedCorePrefixedAliases -and (Test-IsCoreAliasTargetPath -RuntimePath $runtimeTargetPath)
            if ($null -ne $targetDecision.Reason -or $isCoreAliasTarget) {
                if ($isCoreAliasTarget -and $null -eq $targetDecision.Reason) {
                    $targetDecision = [pscustomobject]@{
                        RuntimePath = $targetDecision.RuntimePath
                        Exists = $targetDecision.Exists
                        RuntimeLengthBefore = $targetDecision.RuntimeLengthBefore
                        RuntimeWriteUtcBefore = $targetDecision.RuntimeWriteUtcBefore
                        Reason = "refresh-core-alias-hardlink"
                        SourceSha256 = $targetDecision.SourceSha256
                        RuntimeSha256 = $targetDecision.RuntimeSha256
                    }
                }
                $targetDecision
            }
        }
    )

    $archiveAction = "unchanged"
    $copyResultsByPath = @{}
    if ($targetDecisions.Count -gt 0) {
        $plannedArchives.Add($archiveId) | Out-Null
        $plannedTargetCount += $targetDecisions.Count
        if ($CheckOnly) {
            $archiveAction = "would-copy"
        } else {
            $hadCopyFailure = $false
            foreach ($targetDecision in $targetDecisions) {
                $isCoreAliasTarget = $SeedCorePrefixedAliases -and (Test-IsCoreAliasTargetPath -RuntimePath $targetDecision.RuntimePath)
                $copyResult = if ($isCoreAliasTarget) {
                    Try-ReplaceRuntimeAliasWithHardLink -PrimaryRuntimePath $primaryRuntimePath -AliasRuntimePath $targetDecision.RuntimePath
                } else {
                    Try-CopyRuntimeArchive -SourcePath $sourceFile.FullName -RuntimePath $targetDecision.RuntimePath
                }
                $copyResultsByPath[$targetDecision.RuntimePath] = $copyResult
                if ($copyResult.Success) {
                    if (-not $isCoreAliasTarget) {
                        $copiedBytes += [int64]$sourceFile.Length
                    }
                    $copiedTargetCount += 1
                } else {
                    $hadCopyFailure = $true
                    $failedTargetCount += 1
                    $copyErrors.Add([pscustomobject]@{
                        Archive = $archiveId
                        SourcePath = $sourceFile.FullName
                        RuntimePath = $targetDecision.RuntimePath
                        Reason = $copyResult.Reason
                        ErrorMessage = $copyResult.ErrorMessage
                    }) | Out-Null
                }
            }
            if ($hadCopyFailure) {
                $failedArchives.Add($archiveId) | Out-Null
                $archiveAction = "copy-failed"
            } else {
                $copiedArchives.Add($archiveId) | Out-Null
                $archiveAction = "copied"
            }
        }
    } else {
        $unchangedCount += 1
    }

    foreach ($runtimeTargetPath in $runtimeTargetPaths) {
        $targetDecision = $targetDecisions | Where-Object { $_.RuntimePath -eq $runtimeTargetPath } | Select-Object -First 1
        if ($null -ne $targetDecision) {
            $isCoreAliasTarget = $SeedCorePrefixedAliases -and (Test-IsCoreAliasTargetPath -RuntimePath $runtimeTargetPath)
            $targetAction = if ($CheckOnly) {
                if ($isCoreAliasTarget) { "would-hardlink-alias" } else { "would-copy" }
            } else {
                $copyResult = $copyResultsByPath[$runtimeTargetPath]
                if ($copyResult -and -not $copyResult.Success) {
                    $copyResult.Reason
                } elseif ($isCoreAliasTarget) {
                    "hardlinked-alias"
                } elseif ($archiveAction -eq "copied") {
                    "copied"
                } else {
                    "copy-failed"
                }
            }
        } else {
            $targetState = Get-RuntimeTargetState -RuntimePath $runtimeTargetPath
            $targetDecision = [pscustomobject]@{
                RuntimePath = $runtimeTargetPath
                Exists = $targetState.Exists
                RuntimeLengthBefore = $targetState.RuntimeLengthBefore
                RuntimeWriteUtcBefore = $targetState.RuntimeWriteUtcBefore
                Reason = $null
                SourceSha256 = $null
                RuntimeSha256 = $null
            }
            $targetAction = "unchanged"
            $unchangedTargetCount += 1
        }

        $entries.Add([pscustomobject]@{
            Archive = $archiveId
            SourcePath = $sourceFile.FullName
            RuntimePath = $runtimeTargetPath
            RuntimeTargetPaths = @($runtimeTargetPaths)
            RuntimeTargetName = Split-Path -Leaf $runtimeTargetPath
            SourceLength = $sourceFile.Length
            RuntimeLengthBefore = $targetDecision.RuntimeLengthBefore
            SourceWriteUtc = $sourceWriteUtc
            RuntimeWriteUtcBefore = $targetDecision.RuntimeWriteUtcBefore
            Action = $targetAction
            ArchiveAction = $archiveAction
            Reason = if (-not $CheckOnly -and $copyResultsByPath.ContainsKey($runtimeTargetPath) -and -not $copyResultsByPath[$runtimeTargetPath].Success) {
                $copyResultsByPath[$runtimeTargetPath].Reason
            } else {
                $targetDecision.Reason
            }
            SourceSha256 = $targetDecision.SourceSha256
            RuntimeSha256 = $targetDecision.RuntimeSha256
        }) | Out-Null
    }
}

$summary = [pscustomobject]@{
    SourceCacheDir = $SourceCacheDir
    RuntimeCacheDir = $RuntimeCacheDir
    CheckOnly = [bool]$CheckOnly
    SeedMissingOnly = [bool]$SeedMissingOnly
    SeedCorePrefixedAliases = [bool]$SeedCorePrefixedAliases
    RescueSkippedBootstrapStubs = [bool]$RescueSkippedBootstrapStubs
    ValidateSkippedArchives = $effectiveValidateSkippedArchives
    BootstrapStubMaxLength = $BootstrapStubMaxLength
    SkipJs5Archives = @($SkipJs5Archives)
    SourceFileCount = $sourceFiles.Count
    PlannedCopyCount = $plannedArchives.Count
    CopiedCount = $copiedArchives.Count
    RescuedCount = $rescuedArchives.Count
    ValidatedSkippedCount = $validatedSkippedArchives.Count
    FailedCount = $failedArchives.Count
    SkippedCount = $skippedArchives.Count
    UnchangedCount = $unchangedCount
    PlannedTargetCount = $plannedTargetCount
    CopiedTargetCount = $copiedTargetCount
    FailedTargetCount = $failedTargetCount
    SkippedTargetCount = $skippedTargetCount
    UnchangedTargetCount = $unchangedTargetCount
    CopiedBytes = $copiedBytes
    RepairedExistingCoreAliasCount = $repairedExistingCoreAliasCount
    RepairedExistingCoreAliasBytes = $repairedExistingCoreAliasBytes
    PlannedArchives = @($plannedArchives.ToArray())
    CopiedArchives = @($copiedArchives.ToArray())
    RescuedArchives = @($rescuedArchives.ToArray())
    ValidatedSkippedArchives = @($validatedSkippedArchives.ToArray())
    FailedArchives = @($failedArchives.ToArray())
    SkippedArchives = @($skippedArchives.ToArray())
    CopyErrors = @($copyErrors.ToArray())
    RepairedExistingCoreAliasErrors = @($repairedExistingCoreAliasErrors.ToArray())
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
