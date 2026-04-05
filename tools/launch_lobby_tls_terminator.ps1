param(
    [string]$ListenHost = "127.0.0.1,::1",
    [int]$ListenPort = 443,
    [string]$RemoteHost = "127.0.0.1",
    [int]$RemotePort = 43594,
    [string]$Name = "lobby",
    [string]$LobbyHost = "localhost",
    [string]$TlsRemoteHost = "content.runescape.com",
    [string[]]$TlsExtraMitmHost = @(),
    [int]$TlsRemotePort = 443,
    [string]$TlsConnectHost = "",
    [int]$TlsConnectPort = 0,
    [string]$SecureGamePassthroughHost = "",
    [int]$SecureGamePassthroughPort = 0,
    [string]$SecureGameDecryptedHost = "",
    [int]$SecureGameDecryptedPort = 0,
    [switch]$TlsPassthrough,
    [switch]$TlsRemoteRaw,
    [switch]$AllowRetailJs5Upstream,
    [switch]$InlineProxy,
    [int]$MaxSessions = 0,
    [int]$IdleTimeoutSeconds = 0,
    [double]$SocketTimeout = 180,
    [int]$RawClientByteCap = 0,
    [double]$RawClientByteCapShutdownDelaySeconds = 0
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$tlsDir = Join-Path $root "data\tls"
$outputDir = Join-Path $root ("data\debug\{0}-tls-terminator" -f $Name)
$stdout = Join-Path $root ("tmp-{0}-tls-terminator.out.log" -f $Name)
$stderr = Join-Path $root ("tmp-{0}-tls-terminator.err.log" -f $Name)
$traceLog = Join-Path $root ("tmp-{0}-tls-terminator.trace.log" -f $Name)
$certScript = Join-Path $PSScriptRoot "setup_lobby_tls_cert.ps1"
$proxyScriptPath = Join-Path $PSScriptRoot "tls_terminate_proxy.py"
$defaultMitmPrimaryHost = "localhost"
$TlsExtraMitmHost = @(
    $TlsExtraMitmHost |
        ForEach-Object { [string]$_ -split "," } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        ForEach-Object { $_.Trim() } |
        Select-Object -Unique
)
$certificateDnsNames = @(
    $LobbyHost
    $TlsRemoteHost
    $TlsExtraMitmHost
    "rs.config.runescape.com"
    "localhost"
    "127.0.0.1"
    "::1"
    "content.runescape.com"
) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Select-Object -Unique

Remove-Item $traceLog -ErrorAction SilentlyContinue

function Write-LauncherTrace {
    param([string]$Message)

    $timestamp = Get-Date -Format "HH:mm:ss.fff"
    Add-Content -Path $traceLog -Value ("{0} {1}" -f $timestamp, $Message)
}

function Resolve-CanonicalMitmPrimaryDnsName {
    param([string]$ResolvedLobbyHost)

    # The no-hosts MITM route rewrites the client-facing content host to
    # localhost, so keep the primary certificate identity loopback-stable and
    # rely on SAN entries for upstream host compatibility.
    return $defaultMitmPrimaryHost
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

$resolvedPrimaryDnsName = Resolve-CanonicalMitmPrimaryDnsName -ResolvedLobbyHost $LobbyHost

function Get-CertInfo {
    param([switch]$CheckOnly)

    Write-LauncherTrace ("Get-CertInfo checkOnly={0}" -f $CheckOnly.IsPresent)
    $certInfoJson = & $certScript `
        -DnsName $certificateDnsNames `
        -PrimaryDnsName $resolvedPrimaryDnsName `
        -CheckOnly:$CheckOnly
    return ($certInfoJson | ConvertFrom-Json)
}

Write-LauncherTrace ("launcher-start name={0} listenPort={1} tlsRemoteHost={2} extraMitmHosts={3}" -f $Name, $ListenPort, $TlsRemoteHost, ($TlsExtraMitmHost -join ","))

$certInfo = Get-CertInfo -CheckOnly
$sanSet = @($certInfo.SanSet)
$trustHealthy = (
    [bool]$certInfo.TrustHealthy -and
    -not [string]::IsNullOrWhiteSpace([string]$certInfo.PfxPath) -and
    (Test-Path ([string]$certInfo.PfxPath)) -and
    -not [string]::IsNullOrWhiteSpace([string]$certInfo.CerPath) -and
    (Test-Path ([string]$certInfo.CerPath)) -and
    [bool]$certInfo.RootTrusted -and
    [bool]$certInfo.DirectLeafTrusted -and
    ($sanSet -contains "localhost") -and
    ($sanSet -contains "content.runescape.com")
)

Write-LauncherTrace ("checkOnly trustHealthy={0} thumbprint={1} sanSet={2}" -f $trustHealthy, $certInfo.ActiveThumbprint, ($sanSet -join ","))

if (-not $trustHealthy) {
    Write-LauncherTrace "checkOnly trust unhealthy -> repair"
    $certInfo = Get-CertInfo
}

$activePrimaryDnsName = [string]$certInfo.PrimaryDnsName
if ([string]::IsNullOrWhiteSpace($activePrimaryDnsName)) {
    throw "Canonical MITM certificate setup did not return a primary DNS name."
}

$activePfxPath = [string]$certInfo.PfxPath
$activeCerPath = [string]$certInfo.CerPath
if ([string]::IsNullOrWhiteSpace($activePfxPath) -or -not (Test-Path $activePfxPath)) {
    throw "Canonical MITM certificate is missing at $activePfxPath"
}
if ([string]::IsNullOrWhiteSpace($activeCerPath) -or -not (Test-Path $activeCerPath)) {
    throw "Canonical MITM certificate is missing at $activeCerPath"
}
if (-not [bool]$certInfo.RootTrusted) {
    throw "Canonical MITM certificate thumbprint $($certInfo.ActiveThumbprint) is missing from Cert:\\CurrentUser\\Root"
}
if (-not [bool]$certInfo.DirectLeafTrusted) {
    throw "Canonical MITM certificate leaf thumbprint $($certInfo.ActiveThumbprint) is not directly trusted in Cert:\\CurrentUser\\TrustedPeople or Cert:\\CurrentUser\\Root"
}
$sanSet = @($certInfo.SanSet)
foreach ($requiredSan in @("localhost", "content.runescape.com", "rs.config.runescape.com")) {
    if ($sanSet -notcontains $requiredSan) {
        throw "Canonical MITM certificate SAN mismatch. Missing $requiredSan in $($sanSet -join ', ')"
    }
}
if (-not [bool]$certInfo.TrustHealthy) {
    throw "Canonical MITM trust is unhealthy for thumbprint $($certInfo.ActiveThumbprint)"
}

Get-ListeningProcessIds -Ports @($ListenPort) |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {
        }
    }

Get-ProxyProcessIdsForListenPort -ListenPort $ListenPort |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {
        }
    }

Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue
Write-LauncherTrace "cleared prior stdout/stderr"

if ([string]::IsNullOrWhiteSpace($TlsConnectHost) -and -not [string]::IsNullOrWhiteSpace($TlsRemoteHost)) {
    try {
        $currentIps = @(Resolve-DnsName $TlsRemoteHost -Type A -ErrorAction Stop | Select-Object -ExpandProperty IPAddress)
        if ($currentIps -contains "127.0.0.1") {
            $TlsConnectHost = Resolve-DnsName $TlsRemoteHost -Type A -Server 1.1.1.1 -ErrorAction Stop |
                Select-Object -ExpandProperty IPAddress -First 1
        }
    } catch {
    }
}

$pythonExe = (Get-Command python).Source
$pythonInvokeArgs = @(
    $proxyScriptPath,
    "--listen-host", $ListenHost,
    "--listen-port", $ListenPort.ToString(),
    "--remote-host", $RemoteHost,
    "--remote-port", $RemotePort.ToString(),
    "--tls-remote-host", $TlsRemoteHost,
    "--tls-remote-port", $TlsRemotePort.ToString(),
    "--tls-extra-mitm-host", "rs.config.runescape.com",
    "--pfxfile", $certInfo.PfxPath,
    "--pfxpassword", $certInfo.PfxPassword,
    "--output-dir", $outputDir,
    "--max-sessions", $MaxSessions.ToString(),
    "--idle-timeout-seconds", $IdleTimeoutSeconds.ToString(),
    "--socket-timeout", $SocketTimeout.ToString(),
    "--raw-client-byte-cap", $RawClientByteCap.ToString(),
    "--raw-client-byte-cap-shutdown-delay-seconds", $RawClientByteCapShutdownDelaySeconds.ToString()
)
$extraMitmHosts = @(
    $TlsExtraMitmHost |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        ForEach-Object { $_.Trim() } |
        Select-Object -Unique
)
foreach ($extraMitmHost in $extraMitmHosts) {
    $pythonInvokeArgs += @("--tls-extra-mitm-host", $extraMitmHost)
}
$argString = (
    '"{0}" --listen-host "{1}" --listen-port {2} ' +
    '--remote-host {3} --remote-port {4} ' +
    '--tls-remote-host {5} --tls-remote-port {6} ' +
    '--pfxfile "{7}" --pfxpassword "{8}" --output-dir "{9}" ' +
    '--max-sessions {10} --idle-timeout-seconds {11} --socket-timeout {12} ' +
    '--raw-client-byte-cap {13} --raw-client-byte-cap-shutdown-delay-seconds {14}'
) -f (
    $proxyScriptPath,
    $ListenHost,
    $ListenPort,
    $RemoteHost,
    $RemotePort,
    $TlsRemoteHost,
    $TlsRemotePort,
    $certInfo.PfxPath,
    $certInfo.PfxPassword,
    $outputDir,
    $MaxSessions,
    $IdleTimeoutSeconds,
    $SocketTimeout,
    $RawClientByteCap,
    $RawClientByteCapShutdownDelaySeconds
)
foreach ($extraMitmHost in $extraMitmHosts) {
    $argString += (' --tls-extra-mitm-host "{0}"' -f $extraMitmHost)
}
if (-not [string]::IsNullOrWhiteSpace($TlsConnectHost)) {
    $pythonInvokeArgs += @("--tls-connect-host", $TlsConnectHost)
    $argString += (' --tls-connect-host "{0}"' -f $TlsConnectHost)
}
if ($TlsConnectPort -gt 0) {
    $pythonInvokeArgs += @("--tls-connect-port", $TlsConnectPort.ToString())
    $argString += (' --tls-connect-port {0}' -f $TlsConnectPort)
}
if (-not [string]::IsNullOrWhiteSpace($SecureGamePassthroughHost)) {
    $pythonInvokeArgs += @("--secure-game-passthrough-host", $SecureGamePassthroughHost)
    $argString += (' --secure-game-passthrough-host "{0}"' -f $SecureGamePassthroughHost)
}
if ($SecureGamePassthroughPort -gt 0) {
    $pythonInvokeArgs += @("--secure-game-passthrough-port", $SecureGamePassthroughPort.ToString())
    $argString += (' --secure-game-passthrough-port {0}' -f $SecureGamePassthroughPort)
}
if (-not [string]::IsNullOrWhiteSpace($SecureGameDecryptedHost)) {
    $pythonInvokeArgs += @("--secure-game-decrypted-host", $SecureGameDecryptedHost)
    $argString += (' --secure-game-decrypted-host "{0}"' -f $SecureGameDecryptedHost)
}
if ($SecureGameDecryptedPort -gt 0) {
    $pythonInvokeArgs += @("--secure-game-decrypted-port", $SecureGameDecryptedPort.ToString())
    $argString += (' --secure-game-decrypted-port {0}' -f $SecureGameDecryptedPort)
}
if ($TlsPassthrough) {
    $pythonInvokeArgs += "--tls-passthrough"
    $argString += ' --tls-passthrough'
}
if ($TlsRemoteRaw) {
    $pythonInvokeArgs += "--tls-remote-raw"
    $argString += ' --tls-remote-raw'
}
if ($AllowRetailJs5Upstream) {
    $pythonInvokeArgs += "--allow-retail-js5-upstream"
    $argString += ' --allow-retail-js5-upstream'
}

if ($InlineProxy) {
    Write-LauncherTrace "inline-proxy-start"
    & $pythonExe @pythonInvokeArgs
    exit $LASTEXITCODE
}

Write-LauncherTrace ("starting python proxy exe={0}" -f $pythonExe)
$process = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList ((@($pythonInvokeArgs) | ForEach-Object { Quote-CmdArgument $_ }) -join " ") `
    -WorkingDirectory $PSScriptRoot `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru
Write-LauncherTrace ("started python proxy pid={0}" -f $process.Id)

$listenerProcessIds = Wait-ListeningProcessIds -Port $ListenPort -TimeoutSeconds 15
if ($listenerProcessIds.Count -eq 0) {
    Write-LauncherTrace ("bind-timeout pid={0}" -f $process.Id)
    try {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {
    }
    throw "Timed out waiting for the lobby TLS proxy to bind $ListenPort."
}

Write-LauncherTrace ("listener-ready pid={0}" -f $listenerProcessIds[0])

$json = [pscustomobject]@{
    ProcessId = $listenerProcessIds[0]
    ListenHost = $ListenHost
    ListenPort = $ListenPort
    RemoteHost = $RemoteHost
    RemotePort = $RemotePort
    MaxSessions = $MaxSessions
    IdleTimeoutSeconds = $IdleTimeoutSeconds
    SocketTimeout = $SocketTimeout
    RawClientByteCap = $RawClientByteCap
    RawClientByteCapShutdownDelaySeconds = $RawClientByteCapShutdownDelaySeconds
    TlsRemoteHost = $TlsRemoteHost
    TlsExtraMitmHost = if ($extraMitmHosts.Count -gt 0) { $extraMitmHosts } else { $null }
    TlsRemotePort = $TlsRemotePort
    TlsConnectHost = $TlsConnectHost
    TlsConnectPort = if ($TlsConnectPort -gt 0) { $TlsConnectPort } else { $null }
    SecureGamePassthroughHost = if (-not [string]::IsNullOrWhiteSpace($SecureGamePassthroughHost)) { $SecureGamePassthroughHost } else { $null }
    SecureGamePassthroughPort = if ($SecureGamePassthroughPort -gt 0) { $SecureGamePassthroughPort } else { $null }
    SecureGameDecryptedHost = if (-not [string]::IsNullOrWhiteSpace($SecureGameDecryptedHost)) { $SecureGameDecryptedHost } else { $null }
    SecureGameDecryptedPort = if ($SecureGameDecryptedPort -gt 0) { $SecureGameDecryptedPort } else { $null }
    TlsRemoteRaw = $TlsRemoteRaw.IsPresent
    AllowRetailJs5Upstream = $AllowRetailJs5Upstream.IsPresent
    Stdout = $stdout
    Stderr = $stderr
    PfxFile = $certInfo.PfxPath
    TlsCertThumbprint = $certInfo.ActiveThumbprint
    TlsCertSubject = $certInfo.ActiveSubject
    TrustHealthy = [bool]$certInfo.TrustHealthy
    OutputDir = $outputDir
    LaunchMode = "start-process-python"
} | ConvertTo-Json -Depth 3

Write-Output $json
