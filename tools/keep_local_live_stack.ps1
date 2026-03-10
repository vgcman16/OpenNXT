param(
    [int]$CheckIntervalSeconds = 2
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$powershellExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$lobbyProxyScript = Join-Path $PSScriptRoot "launch_lobby_tls_terminator.ps1"
$gameProxyScript = Join-Path $PSScriptRoot "launch_game_tls_terminator.ps1"
$gameProxyPython = Join-Path $PSScriptRoot "tcp_proxy.py"
$gameProxyOut = Join-Path $root "tmp-game-proxy.out.log"
$gameProxyErr = Join-Path $root "tmp-game-proxy.err.log"

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($false, "Global\OpenNXTLiveProxyWatchdog", [ref]$createdNew)
if (-not $createdNew) {
    Write-Output "watchdog=already-running"
    exit 0
}

function Test-PortListening {
    param([int]$Port)

    return $null -ne (
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -eq $Port } |
            Select-Object -First 1
    )
}

function Start-LobbyProxy {
    & $powershellExe -ExecutionPolicy Bypass -File $lobbyProxyScript -MaxSessions 4096 -IdleTimeoutSeconds 28800 | Out-Null
}

function Start-GameProxy {
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq 43595 } |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            try {
                taskkill /PID $_ /F | Out-Null
            } catch {
            }
        }

    Remove-Item $gameProxyOut, $gameProxyErr -ErrorAction SilentlyContinue

    Start-Process -FilePath "python" `
        -ArgumentList @(
            ('"{0}"' -f $gameProxyPython),
            "--listen-host", "127.0.0.1",
            "--listen-port", "43595",
            "--remote-host", "127.0.0.1",
            "--remote-port", "43596"
        ) `
        -WorkingDirectory $root `
        -RedirectStandardOutput $gameProxyOut `
        -RedirectStandardError $gameProxyErr `
        -PassThru | Out-Null
}

try {
    Write-Output "watchdog=started intervalSeconds=$CheckIntervalSeconds"
    while ($true) {
        try {
            $serverReady = (Test-PortListening -Port 8081) -and (Test-PortListening -Port 43596)
            if ($serverReady) {
                if (-not (Test-PortListening -Port 43595)) {
                    Write-Output "watchdog=restarting game proxy"
                    Start-GameProxy
                }
                if (-not (Test-PortListening -Port 443)) {
                    Write-Output "watchdog=restarting lobby proxy"
                    Start-LobbyProxy
                }
            }
        } catch {
            Write-Error $_
        }

        Start-Sleep -Seconds $CheckIntervalSeconds
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
