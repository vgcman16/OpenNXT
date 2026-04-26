param(
    [int]$TargetPid = 0,
    [string]$ProcessName = "rs2client.exe",
    [int]$MaxDumps = 1,
    [switch]$FirstChance,
    [switch]$DumpOnTerminate,
    [switch]$WaitForProcess
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$defaultOutputRoot = Join-Path $root "data\debug\userdumps\947-client-only"

function Resolve-ProcDumpExe {
    $candidates = @(
        (Join-Path $env:USERPROFILE "Tools\bin\procdump.exe"),
        "C:\Users\skull\Tools\bin\procdump.exe"
    )

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    $command = Get-Command procdump -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $command = Get-Command procdump.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Could not resolve procdump.exe"
}

function Quote-Argument {
    param([string]$Value)

    if ($null -eq $Value) {
        return '""'
    }

    return '"' + ($Value -replace '"', '\"') + '"'
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = Join-Path $defaultOutputRoot $timestamp
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

$stdoutLog = Join-Path $outputDir "procdump.stdout.log"
$stderrLog = Join-Path $outputDir "procdump.stderr.log"
$procdumpExe = Resolve-ProcDumpExe

$arguments = @(
    "-accepteula",
    "-ma",
    "-e",
    "-g",
    "-n", $MaxDumps
)

if ($FirstChance.IsPresent) {
    $arguments += "1"
}

if ($DumpOnTerminate.IsPresent) {
    $arguments += "-t"
}

if ($TargetPid -gt 0) {
    $arguments += @($TargetPid, (Quote-Argument $outputDir))
    $mode = "attach"
}
else {
    $arguments += @("-w", $ProcessName, (Quote-Argument $outputDir))
    $mode = "wait"
}

if ($WaitForProcess.IsPresent -and $TargetPid -le 0) {
    $mode = "wait"
}

$process = Start-Process -FilePath $procdumpExe `
    -ArgumentList $arguments `
    -WorkingDirectory $root `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

[pscustomobject]@{
    MonitorPid = $process.Id
    Mode = $mode
    DumpOnTerminate = $DumpOnTerminate.IsPresent
    TargetPid = $(if ($TargetPid -gt 0) { $TargetPid } else { $null })
    ProcessName = $(if ($TargetPid -gt 0) { $null } else { $ProcessName })
    OutputDir = $outputDir
    StdoutLog = $stdoutLog
    StderrLog = $stderrLog
    ProcDumpExe = $procdumpExe
} | ConvertTo-Json
