param(
    [int]$CheckIntervalSeconds = 2,
    [switch]$LobbyTlsPassthrough,
    [switch]$BypassGameProxy
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$powershellExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$lobbyProxyScript = Join-Path $PSScriptRoot "launch_lobby_tls_terminator.ps1"
$gameProxyScript = Join-Path $PSScriptRoot "launch_game_tls_terminator.ps1"
$gameProxyOut = Join-Path $root "tmp-game-proxy.out.log"
$gameProxyErr = Join-Path $root "tmp-game-proxy.err.log"
$serverConfigPath = Join-Path $root "data\config\server.toml"
$defaultMitmPrimaryHost = "localhost"

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($false, "Global\OpenNXTLiveProxyWatchdog", [ref]$createdNew)
if (-not $createdNew) {
    Write-Output "watchdog=already-running"
    exit 0
}

function Get-PortFromEndpoint {
    param([string]$Endpoint)

    if ($Endpoint -match ':(\d+)$') {
        return [int]$Matches[1]
    }

    return $null
}

function Get-ListeningProcessIds {
    param([int[]]$Ports)

    $processIds = @()
    foreach ($line in (netstat -ano -p tcp)) {
        if ($line -notmatch '^\s*TCP\s+') {
            continue
        }

        $parts = ($line -replace '^\s+', '') -split '\s+'
        if ($parts.Length -lt 5) {
            continue
        }

        if ($parts[3] -ne "LISTENING") {
            continue
        }

        $localPort = Get-PortFromEndpoint $parts[1]
        if ($null -eq $localPort -or $localPort -notin $Ports) {
            continue
        }

        $processId = 0
        if ([int]::TryParse($parts[4], [ref]$processId)) {
            $processIds += $processId
        }
    }

    return @($processIds | Select-Object -Unique)
}

function Test-PortListening {
    param([int]$Port)

    return (Get-ListeningProcessIds -Ports @($Port)).Count -gt 0
}

function Get-ConfiguredPort {
    param(
        [string]$Path,
        [string]$Key,
        [int]$DefaultValue
    )

    if (-not (Test-Path $Path)) {
        return $DefaultValue
    }

    foreach ($line in (Get-Content $Path)) {
        if ($line -match ('^\s*{0}\s*=\s*(\d+)' -f [Regex]::Escape($Key))) {
            return [int]$Matches[1]
        }
    }

    return $DefaultValue
}

$configuredHttpPort = Get-ConfiguredPort -Path $serverConfigPath -Key "http" -DefaultValue 8081
$configuredGamePort = Get-ConfiguredPort -Path $serverConfigPath -Key "game" -DefaultValue 43594
$configuredGameBackendPort = Get-ConfiguredPort -Path $serverConfigPath -Key "gameBackend" -DefaultValue 43596

function Start-LobbyProxy {
    $rawRemotePort = if ($configuredGameBackendPort -gt 0) { $configuredGameBackendPort } else { $configuredGamePort }
    $lobbyProxyArgs = @(
        "-LobbyHost",
        $defaultMitmPrimaryHost,
        "-RemoteHost",
        "127.0.0.1",
        "-RemotePort",
        $rawRemotePort.ToString(),
        "-MaxSessions",
        "0",
        "-IdleTimeoutSeconds",
        "0"
    )

    if ($LobbyTlsPassthrough) {
        $lobbyProxyArgs += "-TlsPassthrough"
    } else {
        $lobbyProxyArgs += @(
            "-TlsRemoteHost",
            "content.runescape.com",
            "-TlsRemotePort",
            "443",
            "-TlsConnectHost",
            "127.0.0.1",
            "-TlsConnectPort",
            $configuredHttpPort.ToString(),
            "-TlsRemoteRaw"
        )
    }

    & $lobbyProxyScript @lobbyProxyArgs | Out-Null
}

function Start-GameProxy {
    Get-ListeningProcessIds -Ports @($configuredGamePort) |
        ForEach-Object {
            try {
                taskkill /PID $_ /F | Out-Null
            } catch {
            }
        }

    Remove-Item $gameProxyOut, $gameProxyErr -ErrorAction SilentlyContinue
    Start-Process -FilePath $powershellExe `
        -ArgumentList @(
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ('"{0}"' -f $gameProxyScript)
        ) `
        -WorkingDirectory $root | Out-Null
}

try {
    Write-Output "watchdog=started intervalSeconds=$CheckIntervalSeconds lobbyTlsPassthrough=$($LobbyTlsPassthrough.IsPresent) bypassGameProxy=$($BypassGameProxy.IsPresent)"
    while ($true) {
        try {
            $serverReady = (Test-PortListening -Port $configuredHttpPort) -and (Test-PortListening -Port $configuredGameBackendPort)
            if ($serverReady) {
                if (-not $BypassGameProxy -and -not (Test-PortListening -Port $configuredGamePort)) {
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
