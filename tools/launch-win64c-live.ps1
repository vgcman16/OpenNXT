param()

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$powershellExe = "$env:WINDIR\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
$serverOut = Join-Path $root "tmp-manual-js5.out.log"
$serverErr = Join-Path $root "tmp-manual-js5.err.log"
$lobbyProxyScript = Join-Path $PSScriptRoot "launch_lobby_tls_terminator.ps1"
$gameProxyScript = Join-Path $PSScriptRoot "launch_game_tls_terminator.ps1"
$watchdogScript = Join-Path $PSScriptRoot "keep_local_live_stack.ps1"
$watchdogOut = Join-Path $root "tmp-live-stack-watchdog.out.log"
$watchdogErr = Join-Path $root "tmp-live-stack-watchdog.err.log"
$clientDir = Join-Path $root "data\\clients\\946\\win64c\\patched"
$clientExe = Join-Path $clientDir "rs2client.exe"
$launchArg = "http://127.0.0.1:8081/jav_config.ws?binaryType=6"

function Wait-ListeningPorts {
    param(
        [int[]]$Ports,
        [int]$Retries = 60,
        [int]$DelayMilliseconds = 500
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        Start-Sleep -Milliseconds $DelayMilliseconds
        $listening = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -in $Ports } |
            Select-Object -ExpandProperty LocalPort -Unique |
            Sort-Object

        if (($listening -join ",") -eq (($Ports | Sort-Object) -join ",")) {
            return $true
        }
    }

    return $false
}

function Start-LobbyProxy {
    & $powershellExe -ExecutionPolicy Bypass -File $lobbyProxyScript -MaxSessions 4096 -IdleTimeoutSeconds 28800 | Out-Null
}

function Start-GameProxy {
    & $powershellExe -ExecutionPolicy Bypass -File $gameProxyScript | Out-Null
}

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 443, 8081, 43595, 43596 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {}
    }

Get-Process -Name rs2client -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        taskkill /PID $_.Id /F | Out-Null
    } catch {}
}

Remove-Item $serverOut, $serverErr -ErrorAction SilentlyContinue

$wrapper = Start-Process -FilePath (Join-Path $root "build\\install\\OpenNXT\\bin\\OpenNXT.bat") `
    -ArgumentList "run-server" `
    -WorkingDirectory $root `
    -RedirectStandardOutput $serverOut `
    -RedirectStandardError $serverErr `
    -PassThru

$serverPid = $null
if (-not (Wait-ListeningPorts -Ports @(8081, 43596))) {
    throw "Timed out waiting for OpenNXT server ports 8081 and 43596"
}

$serverPid = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8081, 43596 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Select-Object -First 1

Start-LobbyProxy
Start-GameProxy

Remove-Item $watchdogOut, $watchdogErr -ErrorAction SilentlyContinue
$watchdog = Start-Process -FilePath $powershellExe `
    -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", ('"{0}"' -f $watchdogScript), "-CheckIntervalSeconds", "2") `
    -WorkingDirectory $root `
    -RedirectStandardOutput $watchdogOut `
    -RedirectStandardError $watchdogErr `
    -PassThru

if (-not (Wait-ListeningPorts -Ports @(443, 43595))) {
    throw "Timed out waiting for proxy ports 443 and 43595"
}

$lobbyProxyPid = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -eq 443 } |
    Select-Object -ExpandProperty OwningProcess -First 1
$gameProxyPid = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -eq 43595 } |
    Select-Object -ExpandProperty OwningProcess -First 1

$client = Start-Process -FilePath $clientExe `
    -ArgumentList $launchArg `
    -WorkingDirectory $clientDir `
    -PassThru

[pscustomobject]@{
    WrapperPid = $wrapper.Id
    ServerPid = $serverPid
    LobbyProxyPid = $lobbyProxyPid
    GameProxyPid = $gameProxyPid
    WatchdogPid = $watchdog.Id
    ClientPid = $client.Id
    ServerOut = $serverOut
    ServerErr = $serverErr
    WatchdogOut = $watchdogOut
    WatchdogErr = $watchdogErr
    ClientExe = $clientExe
    ClientArg = $launchArg
} | ConvertTo-Json -Depth 3
