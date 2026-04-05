param(
    [int]$TargetPid = 0,
    [int]$DurationSeconds = 180,
    [string]$OutputPath = "",
    [string]$LatestOutputPath = "",
    [string]$FunctionStartRva = "0x590bc0",
    [string]$FaultRva = "0x590de8",
    [string]$StateCaptureRva = "0x590dcb",
    [switch]$EnableMissingIndexedTableGuard,
    [string]$GuardCallerSiteRva = "",
    [string]$GuardResumeRva = "",
    [switch]$RepairR15AtStateCapture,
    [switch]$RepairEpilogueFrame,
    [switch]$RepairReleaseFrame,
    [string[]]$ForceSuccessCallerSiteRva = @()
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$traceScript = Join-Path $PSScriptRoot "trace_947_client_crash_probe.py"
$defaultRunsDir = Join-Path $root "data\debug\frida-crash-probe\runs"
$defaultLatestOutput = Join-Path $root "data\debug\frida-crash-probe\latest-client-only.jsonl"

function Resolve-PythonExe {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $command = Get-Command py -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Could not resolve python.exe or py.exe from PATH"
}

function Quote-Argument {
    param([string]$Value)

    if ($null -eq $Value) {
        return '""'
    }

    return '"' + ($Value -replace '"', '\"') + '"'
}

if ($TargetPid -le 0) {
    $process = Get-Process rs2client -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $process) {
        throw "Could not find a running rs2client.exe process"
    }
    $TargetPid = $process.Id
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputPath = Join-Path $defaultRunsDir ("947-client-only-crash-probe-{0}.jsonl" -f $timestamp)
}

if ([string]::IsNullOrWhiteSpace($LatestOutputPath)) {
    $LatestOutputPath = $defaultLatestOutput
}

$outputDir = Split-Path -Parent $OutputPath
$latestDir = Split-Path -Parent $LatestOutputPath
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
New-Item -ItemType Directory -Path $latestDir -Force | Out-Null

$stdoutLog = [System.IO.Path]::ChangeExtension($OutputPath, ".stdout.log")
$stderrLog = [System.IO.Path]::ChangeExtension($OutputPath, ".stderr.log")
$pythonExe = Resolve-PythonExe

$arguments = @(
    (Quote-Argument $traceScript),
    "--pid", $TargetPid,
    "--output", (Quote-Argument $OutputPath),
    "--latest-output", (Quote-Argument $LatestOutputPath),
    "--function-start-rva", $FunctionStartRva,
    "--fault-rva", $FaultRva,
    "--state-capture-rva", $StateCaptureRva
)

if ($DurationSeconds -gt 0) {
    $arguments += @("--duration-seconds", $DurationSeconds)
}

if ($RepairR15AtStateCapture.IsPresent) {
    $arguments += "--repair-r15-at-state-capture"
}

if ($RepairEpilogueFrame.IsPresent) {
    $arguments += "--repair-epilogue-frame"
}

if ($RepairReleaseFrame.IsPresent) {
    $arguments += "--repair-release-frame"
}

if ($EnableMissingIndexedTableGuard.IsPresent) {
    if ([string]::IsNullOrWhiteSpace($GuardCallerSiteRva) -or [string]::IsNullOrWhiteSpace($GuardResumeRva)) {
        throw "EnableMissingIndexedTableGuard requires explicit -GuardCallerSiteRva and -GuardResumeRva values on WIN64"
    }

    $arguments += @(
        "--enable-missing-indexed-table-guard",
        "--guard-caller-site-rva", $GuardCallerSiteRva,
        "--guard-resume-rva", $GuardResumeRva
    )
}

foreach ($callerSiteRva in $ForceSuccessCallerSiteRva) {
    if (-not [string]::IsNullOrWhiteSpace($callerSiteRva)) {
        $arguments += @("--force-success-caller-site-rva", $callerSiteRva)
    }
}

$process = Start-Process -FilePath $pythonExe `
    -ArgumentList $arguments `
    -WorkingDirectory $root `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

[pscustomobject]@{
    TracePid = $process.Id
    TargetPid = $TargetPid
    RepairR15AtStateCapture = $RepairR15AtStateCapture.IsPresent
    RepairEpilogueFrame = $RepairEpilogueFrame.IsPresent
    RepairReleaseFrame = $RepairReleaseFrame.IsPresent
    EnableMissingIndexedTableGuard = $EnableMissingIndexedTableGuard.IsPresent
    GuardCallerSiteRva = $GuardCallerSiteRva
    GuardResumeRva = $GuardResumeRva
    ForceSuccessCallerSiteRva = $ForceSuccessCallerSiteRva
    OutputPath = $OutputPath
    LatestOutputPath = $LatestOutputPath
    StdoutLog = $stdoutLog
    StderrLog = $stderrLog
} | ConvertTo-Json
