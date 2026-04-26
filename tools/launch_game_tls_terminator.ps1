$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$stdout = Join-Path $root "tmp-game-proxy.out.log"
$stderr = Join-Path $root "tmp-game-proxy.err.log"
$tlsDir = Join-Path $root "data\tls"
$outputDir = Join-Path $root "data\debug\game-tls-terminator"
$serverConfigPath = Join-Path $root "data\config\server.toml"
$pfxPath = Join-Path $tlsDir "localhost.pfx"
$pfxPassword = "opennxt-dev"

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

function Get-ProxyProcessIdsForListenPort {
    param([int]$ListenPort)

    return @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $commandLine = [string]$_.CommandLine
                if ($_.Name -notin @("python.exe", "pythonw.exe", "cmd.exe")) {
                    return $false
                }
                if ($commandLine -notlike "*tls_terminate_proxy.py*") {
                    return $false
                }
                $listenPortMatch = [regex]::Match($commandLine, '(?i)(?:^|\s)--listen-port\s+"?(?<port>\d+)"?')
                $listenPortMatch.Success -and ([int]$listenPortMatch.Groups["port"].Value -eq $ListenPort)
            } |
            Select-Object -ExpandProperty ProcessId -Unique
    )
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

function Quote-CmdArgument {
    param([string]$Value)

    if ([string]::IsNullOrEmpty($Value)) {
        return '""'
    }

    if ($Value -match '[\s,"]') {
        return '"' + $Value.Replace('"', '\"') + '"'
    }

    return $Value
}

function Wait-ListeningProcessIds {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 15,
        [int]$DelayMilliseconds = 250
    )

    $deadline = (Get-Date).AddSeconds([Math]::Max(1, $TimeoutSeconds))
    do {
        $processIds = Get-ListeningProcessIds -Ports @($Port)
        if ($processIds.Count -gt 0) {
            return $processIds
        }

        Start-Sleep -Milliseconds $DelayMilliseconds
    } while ((Get-Date) -lt $deadline)

    return @()
}

$listenPort = Get-ConfiguredPort -Path $serverConfigPath -Key "game" -DefaultValue 43594
$remotePort = Get-ConfiguredPort -Path $serverConfigPath -Key "gameBackend" -DefaultValue 43596

if ($listenPort -eq $remotePort) {
    throw "Canonical game TLS route is unhealthy: public game port ($listenPort) matches backend port ($remotePort). Expected a split such as 43594 -> 43596."
}

if (-not (Test-Path $pfxPath)) {
    throw "Canonical localhost MITM certificate is missing at $pfxPath"
}

Get-ListeningProcessIds -Ports @($listenPort) |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {
        }
    }

Get-ProxyProcessIdsForListenPort -ListenPort $listenPort |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {
        }
    }

Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue

$pythonExe = (Get-Command python).Source
$proxyScript = Join-Path $PSScriptRoot "tls_terminate_proxy.py"
$proxyArgs = @(
    $proxyScript,
    "--listen-host",
    "127.0.0.1,::1",
    "--listen-port",
    $listenPort.ToString(),
    "--remote-host",
    "127.0.0.1",
    "--remote-port",
    $remotePort.ToString(),
    "--tls-passthrough",
    "--pfxfile",
    $pfxPath,
    "--pfxpassword",
    $pfxPassword,
    "--output-dir",
    $outputDir,
    "--max-sessions",
    "0",
    "--idle-timeout-seconds",
    "0",
    "--socket-timeout",
    "300"
)
$quotedLaunchParts = (@($pythonExe) + $proxyArgs) | ForEach-Object { Quote-CmdArgument $_ }
$cmdStartLine = 'start "" /b {0}' -f ($quotedLaunchParts -join " ")
Push-Location $PSScriptRoot
try {
    & $env:ComSpec /c $cmdStartLine | Out-Null
} finally {
    Pop-Location
}

$listenerProcessIds = Wait-ListeningProcessIds -Port $listenPort -TimeoutSeconds 15
if ($listenerProcessIds.Count -eq 0) {
    throw "Timed out waiting for the game TLS proxy to bind $listenPort."
}

$json = [pscustomobject]@{
    ProcessId = $listenerProcessIds[0]
    ListenPort = $listenPort
    RemotePort = $remotePort
    LaunchMode = "cmd-start-b"
    Stdout = $stdout
    Stderr = $stderr
} | ConvertTo-Json -Depth 3

Write-Output $json
