param(
    [int]$ClientPid = 0,
    [int]$DurationSeconds = 180,
    [string]$SummaryPath = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($SummaryPath)) {
    $SummaryPath = Join-Path $root "data\debug\direct-rs2client-patch\latest-client-only.json"
}

function Resolve-ClientPid {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return 0
    }

    try {
        $payload = Get-Content -Path $Path -Raw | ConvertFrom-Json
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

if ($ClientPid -le 0) {
    $ClientPid = Resolve-ClientPid -Path $SummaryPath
}

if ($ClientPid -le 0) {
    throw "Could not resolve a live rs2client pid from $SummaryPath"
}

$probeScript = Join-Path $PSScriptRoot "trace_947_lobby_widget_probe.py"
& python $probeScript --pid $ClientPid --duration-seconds $DurationSeconds
