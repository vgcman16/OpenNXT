$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$clientDir = Join-Path $root "data\\clients\\946\\win64c\\patched"
$clientExe = Join-Path $clientDir "rs2client.exe"
$launchArg = "http://127.0.0.1:8081/jav_config.ws?binaryType=6"
$cefRemoteDebuggingPort = 9222
$cefLogFile = Join-Path $root "tmp-rs2client-cef.log"

function Get-RemoteDebugJson {
    param(
        [string]$Uri
    )

    try {
        return Invoke-RestMethod -Uri $Uri -TimeoutSec 2
    } catch {
        return $null
    }
}

$stalePids = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8081, 43595 } |
    Select-Object -ExpandProperty OwningProcess -Unique

foreach ($pid in $stalePids) {
    taskkill /PID $pid /F | Out-Null
}

Get-Process -Name rs2client -ErrorAction SilentlyContinue | ForEach-Object {
    taskkill /PID $_.Id /F | Out-Null
}

if (Test-Path $cefLogFile) {
    Remove-Item $cefLogFile -Force -ErrorAction SilentlyContinue
}

$wrapper = Start-Process -FilePath (Join-Path $root "build\\install\\OpenNXT\\bin\\OpenNXT.bat") `
    -ArgumentList "run-server" `
    -WorkingDirectory $root `
    -PassThru

$serverPid = $null
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    $serverPid = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8081, 43595 } |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Select-Object -First 1
    if ($serverPid) { break }
}

$client = Start-Process -FilePath $clientExe `
    -ArgumentList @(
        $launchArg,
        "--remote-debugging-port=$cefRemoteDebuggingPort",
        "--enable-logging",
        "--log-severity=info",
        "--log-file=$cefLogFile"
    ) `
    -WorkingDirectory $clientDir `
    -PassThru

Start-Sleep -Seconds 12
$clientProcess = Get-Process -Id $client.Id -ErrorAction SilentlyContinue
$cefVersion = Get-RemoteDebugJson -Uri "http://127.0.0.1:$cefRemoteDebuggingPort/json/version"
$cefTargets = @(Get-RemoteDebugJson -Uri "http://127.0.0.1:$cefRemoteDebuggingPort/json/list")

[pscustomobject]@{
    WrapperPid = $wrapper.Id
    ServerPid = $serverPid
    ClientPid = $client.Id
    ClientAlive = $null -ne $clientProcess
    MainWindowTitle = if ($clientProcess) { $clientProcess.MainWindowTitle } else { $null }
    MainWindowHandle = if ($clientProcess) { $clientProcess.MainWindowHandle } else { 0 }
    CefRemoteDebuggingPort = $cefRemoteDebuggingPort
    CefRemoteDebuggingReachable = $null -ne $cefVersion
    CefRemoteDebuggingVersion = $cefVersion
    CefRemoteDebuggingTargets = $cefTargets
    CefLogFile = $cefLogFile
    CefLogTail = if (Test-Path $cefLogFile) { Get-Content $cefLogFile | Select-Object -Last 120 } else { @() }
} | ConvertTo-Json -Depth 4
