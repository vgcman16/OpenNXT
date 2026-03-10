param(
    [int]$ListenPort = 443,
    [string]$RemoteHost = "8.42.17.230",
    [int]$RemotePort = 43596,
    [string]$Name = "lobby",
    [string]$TlsRemoteHost = "content.runescape.com",
    [int]$TlsRemotePort = 443,
    [string]$TlsConnectHost = "",
    [int]$TlsConnectPort = 0,
    [int]$MaxSessions = 4096,
    [int]$IdleTimeoutSeconds = 28800,
    [double]$SocketTimeout = 30
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$tlsDir = Join-Path $root "data\tls"
$outputDir = Join-Path $root ("data\debug\{0}-tls-terminator" -f $Name)
$stdout = Join-Path $root ("tmp-{0}-tls-terminator.out.log" -f $Name)
$stderr = Join-Path $root ("tmp-{0}-tls-terminator.err.log" -f $Name)
$certScript = Join-Path $PSScriptRoot "setup_lobby_tls_cert.ps1"
$proxyScript = Join-Path $PSScriptRoot "tls_terminate_proxy.py"

$certInfoJson = & "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -ExecutionPolicy Bypass -File $certScript
$certInfo = $certInfoJson | ConvertFrom-Json

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -eq $ListenPort } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {
        }
    }

Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue

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

$cmd = 'python "{0}" --listen-host 127.0.0.1 --listen-port {1} --remote-host "{2}" --remote-port {3} --tls-remote-host "{4}" --tls-remote-port {5} --pfxfile "{6}" --pfxpassword "{7}" --output-dir "{8}" --max-sessions {9} --idle-timeout-seconds {10} --socket-timeout {11}' -f $proxyScript, $ListenPort, $RemoteHost, $RemotePort, $TlsRemoteHost, $TlsRemotePort, $certInfo.PfxPath, $certInfo.PfxPassword, $outputDir, $MaxSessions, $IdleTimeoutSeconds, $SocketTimeout
if (-not [string]::IsNullOrWhiteSpace($TlsConnectHost)) {
    $cmd += ' --tls-connect-host "{0}"' -f $TlsConnectHost
}
if ($TlsConnectPort -gt 0) {
    $cmd += ' --tls-connect-port {0}' -f $TlsConnectPort
}

$process = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", $cmd) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

Start-Sleep -Seconds 2

[pscustomobject]@{
    ProcessId = $process.Id
    ListenPort = $ListenPort
    RemoteHost = $RemoteHost
    RemotePort = $RemotePort
    MaxSessions = $MaxSessions
    IdleTimeoutSeconds = $IdleTimeoutSeconds
    SocketTimeout = $SocketTimeout
    TlsRemoteHost = $TlsRemoteHost
    TlsRemotePort = $TlsRemotePort
    TlsConnectHost = $TlsConnectHost
    TlsConnectPort = if ($TlsConnectPort -gt 0) { $TlsConnectPort } else { $null }
    Stdout = $stdout
    Stderr = $stderr
    PfxFile = $certInfo.PfxPath
    OutputDir = $outputDir
} | ConvertTo-Json -Depth 3
