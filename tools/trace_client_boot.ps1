param(
    [string]$ClientVariant = "patched",
    [string]$ConfigUrl = "http://127.0.0.1:8081/jav_config.ws?binaryType=6",
    [int]$DurationSeconds = 20,
    [int]$PollMilliseconds = 250
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$launchScript = Join-Path $PSScriptRoot "launch-client-only.ps1"
$outputDir = Join-Path $root "data\debug\client-boot-trace"
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$tracePath = Join-Path $outputDir ("trace-{0}-{1}.log" -f $ClientVariant, (Get-Date -Format "yyyyMMdd-HHmmss"))

$launchJson = & "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -ExecutionPolicy Bypass `
    -File $launchScript `
    -ClientVariant $ClientVariant `
    -ConfigUrl $ConfigUrl `
    -StartupDelaySeconds 1

$launch = $launchJson | ConvertFrom-Json
$clientPid = [int]$launch.ClientPid
$deadline = (Get-Date).AddSeconds($DurationSeconds)

"launch pid=$clientPid variant=$ClientVariant alive=$($launch.ClientAlive) title=$($launch.MainWindowTitle)" | Set-Content -Path $tracePath

while ((Get-Date) -lt $deadline) {
    $timestamp = Get-Date -Format "HH:mm:ss.fff"
    $process = Get-Process -Id $clientPid -ErrorAction SilentlyContinue

    if ($null -eq $process) {
        Add-Content -Path $tracePath -Value "$timestamp process-exited"
        break
    }

    Add-Content -Path $tracePath -Value ("{0} cpu={1} title={2}" -f $timestamp, $process.CPU, $process.MainWindowTitle)

    $connections = @(Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $clientPid })
    foreach ($connection in $connections) {
        Add-Content -Path $tracePath -Value ("{0} tcp {1}:{2} -> {3}:{4} {5}" -f $timestamp, $connection.LocalAddress, $connection.LocalPort, $connection.RemoteAddress, $connection.RemotePort, $connection.State)
    }

    $udpEndpoints = @()
    try {
        $udpEndpoints = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object { $_.OwningProcess -eq $clientPid })
    } catch {
    }
    foreach ($udpEndpoint in $udpEndpoints) {
        Add-Content -Path $tracePath -Value ("{0} udp {1}:{2}" -f $timestamp, $udpEndpoint.LocalAddress, $udpEndpoint.LocalPort)
    }

    Start-Sleep -Milliseconds $PollMilliseconds
}

[pscustomobject]@{
    TracePath = $tracePath
    ClientPid = $clientPid
    ClientVariant = $ClientVariant
} | ConvertTo-Json -Depth 2
