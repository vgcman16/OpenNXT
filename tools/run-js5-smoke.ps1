param(
    [int]$DurationSeconds = 25,
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$clientDir = Join-Path $root "data\\clients\\946\\win64c\\patched"
$clientExe = Join-Path $clientDir "rs2client.exe"
$launchArg = "http://127.0.0.1:8081/jav_config.ws?binaryType=6"
$serverOut = Join-Path $root "server-js5.out.log"
$serverErr = Join-Path $root "server-js5.err.log"
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

function Stop-StaleProcesses {
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8081, 43595 } |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { taskkill /PID $_ /F | Out-Null }

    Get-Process -Name rs2client -ErrorAction SilentlyContinue | ForEach-Object {
        taskkill /PID $_.Id /F | Out-Null
    }
}

Stop-StaleProcesses

foreach ($path in @($serverOut, $serverErr)) {
    if (Test-Path $path) {
        Remove-Item $path -Force
    }
}

if ($EnableCefLogging -and (Test-Path $cefLogFile)) {
    Remove-Item $cefLogFile -Force -ErrorAction SilentlyContinue
}

$wrapper = $null
$client = $null
$serverPid = $null
$clientArgs = @($launchArg)
$cefVersion = $null
$cefTargets = @()
$cefRemoteDebuggingReachable = $false

if ($CefRemoteDebuggingPort) {
    $clientArgs += "--remote-debugging-port=$CefRemoteDebuggingPort"
}

if ($EnableCefLogging) {
    $clientArgs += "--enable-logging"
    $clientArgs += "--log-severity=info"
    $clientArgs += "--log-file=$cefLogFile"
}

try {
    $wrapper = Start-Process -FilePath (Join-Path $root "build\\install\\OpenNXT\\bin\\OpenNXT.bat") `
        -ArgumentList "run-server" `
        -WorkingDirectory $root `
        -RedirectStandardOutput $serverOut `
        -RedirectStandardError $serverErr `
        -PassThru

    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        $ports = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -in 8081, 43595 } |
            Select-Object -ExpandProperty LocalPort -Unique |
            Sort-Object

        if (($ports -join ",") -eq "8081,43595") {
            $serverPid = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
                Where-Object { $_.LocalPort -in 8081, 43595 } |
                Select-Object -ExpandProperty OwningProcess -Unique |
                Select-Object -First 1
            break
        }
    }

    $client = Start-Process -FilePath $clientExe `
        -ArgumentList $clientArgs `
        -WorkingDirectory $clientDir `
        -PassThru

    for ($i = 0; $i -lt $DurationSeconds; $i++) {
        Start-Sleep -Seconds 1

        if ($CefRemoteDebuggingPort -and -not $cefRemoteDebuggingReachable) {
            $cefVersion = Get-RemoteDebugJson -Uri "http://127.0.0.1:$CefRemoteDebuggingPort/json/version"
            if ($cefVersion) {
                $cefTargets = @(Get-RemoteDebugJson -Uri "http://127.0.0.1:$CefRemoteDebuggingPort/json/list")
                $cefRemoteDebuggingReachable = $true
            }
        }
    }

    $clientProcess = Get-Process -Id $client.Id -ErrorAction SilentlyContinue

    [pscustomobject]@{
        WrapperPid = if ($wrapper) { $wrapper.Id } else { $null }
        ServerPid = $serverPid
        ClientPid = if ($client) { $client.Id } else { $null }
        ClientAlive = $null -ne $clientProcess
        ClientArgs = $clientArgs
        MainWindowTitle = if ($clientProcess) { $clientProcess.MainWindowTitle } else { $null }
        MainWindowHandle = if ($clientProcess) { [int64]$clientProcess.MainWindowHandle } else { 0 }
        ServerOut = $serverOut
        ServerErr = $serverErr
        CefRemoteDebuggingPort = $CefRemoteDebuggingPort
        CefRemoteDebuggingReachable = $cefRemoteDebuggingReachable
        CefRemoteDebuggingVersion = $cefVersion
        CefRemoteDebuggingTargets = $cefTargets
        CefLogFile = if ($EnableCefLogging) { $cefLogFile } else { $null }
        CefLogTail = if ($EnableCefLogging -and (Test-Path $cefLogFile)) { Get-Content $cefLogFile | Select-Object -Last 120 } else { @() }
    } | ConvertTo-Json -Depth 4
} finally {
    Stop-StaleProcesses
}
