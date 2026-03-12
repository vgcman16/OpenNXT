param(
    [int]$DurationSeconds = 20,
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$serverOut = Join-Path $root "tmp-manual-js5.out.log"
$serverErr = Join-Path $root "tmp-manual-js5.err.log"
$clientDir = Join-Path $root "data\\clients\\946\\win64c\\patched"
$clientExe = Join-Path $clientDir "rs2client.exe"
$launchArg = "http://127.0.0.1:8081/jav_config.ws?binaryType=6"
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

function Quote-ProcessArgument {
    param([string]$Value)

    if ([string]::IsNullOrEmpty($Value)) {
        return '""'
    }

    if ($Value.Contains('"')) {
        $Value = $Value.Replace('"', '\"')
    }

    if ($Value -match '\s') {
        return ('"{0}"' -f $Value)
    }

    return $Value
}

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8081, 43595 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { taskkill /PID $_ /F | Out-Null }

Get-Process -Name rs2client -ErrorAction SilentlyContinue | ForEach-Object {
    taskkill /PID $_.Id /F | Out-Null
}

Remove-Item $serverOut, $serverErr -ErrorAction SilentlyContinue
if ($EnableCefLogging -and (Test-Path $cefLogFile)) {
    Remove-Item $cefLogFile -Force -ErrorAction SilentlyContinue
}

$server = $null
$client = $null
$serverPid = $null
$openNxtBat = Join-Path $root "build\\install\\OpenNXT\\bin\\OpenNXT.bat"
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
    $serverCommand = 'set "JAVA_TOOL_OPTIONS=-XX:TieredStopAtLevel=1" && "{0}" run-server' -f $openNxtBat
    $server = Start-Process -FilePath $env:ComSpec `
        -ArgumentList @("/c", $serverCommand) `
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
        -ArgumentList @($clientArgs | ForEach-Object { Quote-ProcessArgument $_ }) `
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
        WrapperPid = if ($server) { $server.Id } else { $null }
        ServerPid = $serverPid
        ClientPid = if ($client) { $client.Id } else { $null }
        ClientAlive = $null -ne $clientProcess
        ClientArgs = $clientArgs
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
    if ($client) {
        taskkill /PID $client.Id /F | Out-Null
    }
    if ($serverPid) {
        taskkill /PID $serverPid /F | Out-Null
    } elseif ($server) {
        taskkill /PID $server.Id /F | Out-Null
    }
}
