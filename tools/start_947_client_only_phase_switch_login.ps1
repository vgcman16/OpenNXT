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
$launchScript = Join-Path $PSScriptRoot "launch-client-only.ps1"
$phaseSwitchScript = Join-Path $PSScriptRoot "run_947_phase_switch_login.py"
$latestClientSummary = Join-Path $root "data\debug\direct-rs2client-patch\latest-client-only.json"
$phaseSummary = Join-Path $root "data\debug\runtek-automation\latest-phase-switch-client-only-login.json"
$phaseTrace = Join-Path $root "data\debug\direct-rs2client-patch\latest-phase-switch-client-only-hook.jsonl"

function Get-ClientPid {
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
    & $launchScript `
        -ClientVariant original `
        -DisableWatchdog `
        -GraphicsCompatibilityMode $true `
        -GraphicsDevicePreference power-saving
}

$deadline = (Get-Date).AddSeconds(120)
$clientPid = 0
do {
    $clientPid = Get-ClientPid -SummaryPath $latestClientSummary
    if ($clientPid -gt 0) {
        $process = Get-Process -Id $clientPid -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            break
        }
    }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

if ($clientPid -le 0) {
    throw "Could not resolve a live rs2client pid from $latestClientSummary"
}

& python $phaseSwitchScript `
    --username $Username `
    --password $Password `
    --window-title $WindowTitle `
    --pid $clientPid `
    --direct-summary-path $latestClientSummary `
    --summary-output $phaseSummary `
    --trace-output $phaseTrace `
    --login-screen-timeout-seconds $LoginScreenTimeoutSeconds `
    --attempt-wait-seconds $AttemptWaitSeconds `
    --trace-duration-seconds $TraceDurationSeconds

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
