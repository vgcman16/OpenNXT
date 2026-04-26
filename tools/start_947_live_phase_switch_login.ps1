param(
    [Parameter(Mandatory = $true)]
    [string]$Username,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    [string]$WindowTitle = "RuneTekApp",
    [int]$LoginScreenTimeoutSeconds = 180,
    [int]$AttemptWaitSeconds = 25,
    [int]$TraceDurationSeconds = 240,
    [switch]$ReuseExistingLaunch
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$launchScript = Join-Path $PSScriptRoot "launch-win64c-live.ps1"
$phaseSwitchScript = Join-Path $PSScriptRoot "run_947_phase_switch_login.py"
$latestLiveSummary = Join-Path $root "data\debug\direct-rs2client-patch\latest-live.json"
$phaseSummary = Join-Path $root "data\debug\runtek-automation\latest-phase-switch-live-login.json"
$phaseTrace = Join-Path $root "data\debug\direct-rs2client-patch\latest-phase-switch-live-hook.jsonl"

function Get-LiveClientPid {
    param([string]$SummaryPath)

    if (-not (Test-Path $SummaryPath)) {
        return 0
    }

    try {
        $payload = Get-Content -Path $SummaryPath -Raw | ConvertFrom-Json
    } catch {
        return 0
    }

    if ($null -eq $payload -or $null -eq $payload.pid) {
        return 0
    }

    try {
        return [int]$payload.pid
    } catch {
        return 0
    }
}

if (-not $ReuseExistingLaunch) {
    & $launchScript -DisableWatchdog
}

$deadline = (Get-Date).AddSeconds(120)
$liveClientPid = 0
do {
    $liveClientPid = Get-LiveClientPid -SummaryPath $latestLiveSummary
    if ($liveClientPid -gt 0) {
        $process = Get-Process -Id $liveClientPid -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            break
        }
    }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

if ($liveClientPid -le 0) {
    throw "Could not resolve a live rs2client pid from $latestLiveSummary"
}

& python $phaseSwitchScript `
    --username $Username `
    --password $Password `
    --window-title $WindowTitle `
    --pid $liveClientPid `
    --direct-summary-path $latestLiveSummary `
    --summary-output $phaseSummary `
    --trace-output $phaseTrace `
    --login-screen-timeout-seconds $LoginScreenTimeoutSeconds `
    --attempt-wait-seconds $AttemptWaitSeconds `
    --trace-duration-seconds $TraceDurationSeconds

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
