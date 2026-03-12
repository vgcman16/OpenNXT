param(
    [switch]$EnableProxySupport,
    [string[]]$ProxyUsernames = @(),
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging,
    [switch]$CaptureConsole,
    [string[]]$ExtraClientArgs = @(),
    [string]$ExtraClientArgsCsv = "",
    [int]$StartupTimeoutSeconds = 90,
    [int]$ProxyStartupTimeoutSeconds = 30
)

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
$proxyConfigPath = Join-Path $root "data\\config\\proxy.toml"
$clientStdout = Join-Path $root "tmp-rs2client.stdout.log"
$clientStderr = Join-Path $root "tmp-rs2client.stderr.log"
$clientCefLog = Join-Path $root "tmp-rs2client-cef.log"
$launchTrace = Join-Path $root "tmp-launch-win64c-live.trace.log"
$launchStateFile = Join-Path $root "tmp-launch-win64c-live.state.json"

function Write-LaunchTrace {
    param([string]$Message)

    Add-Content -Path $launchTrace -Value ("{0} {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $Message)
}

function Get-PortFromEndpoint {
    param([string]$Endpoint)

    if ($Endpoint -match ':(\d+)$') {
        return [int]$Matches[1]
    }

    return $null
}

function Get-NetstatTcpRecords {
    $records = @()

    foreach ($line in (netstat -ano -p tcp)) {
        if ($line -notmatch '^\s*TCP\s+') {
            continue
        }

        $parts = ($line -replace '^\s+', '') -split '\s+'
        if ($parts.Length -lt 5) {
            continue
        }

        $localPort = Get-PortFromEndpoint $parts[1]
        if ($null -eq $localPort) {
            continue
        }

        $owningProcessId = 0
        if (-not [int]::TryParse($parts[4], [ref]$owningProcessId)) {
            continue
        }

        $records += [pscustomobject]@{
            LocalAddress  = $parts[1]
            LocalPort     = $localPort
            RemoteAddress = $parts[2]
            RemotePort    = Get-PortFromEndpoint $parts[2]
            State         = $parts[3]
            OwningProcess = $owningProcessId
        }
    }

    return $records
}

function Get-ListeningProcessIds {
    param([int[]]$Ports)

    return @(
        Get-NetstatTcpRecords |
            Where-Object { $_.State -eq "LISTENING" -and $_.LocalPort -in $Ports } |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Wait-ListeningPorts {
    param(
        [int[]]$Ports,
        [int]$TimeoutSeconds = 30,
        [int]$DelayMilliseconds = 500
    )

    $retries = [Math]::Max(1, [int][Math]::Ceiling(($TimeoutSeconds * 1000) / $DelayMilliseconds))

    for ($i = 0; $i -lt $retries; $i++) {
        Start-Sleep -Milliseconds $DelayMilliseconds
        $listening = Get-NetstatTcpRecords |
            Where-Object { $_.State -eq "LISTENING" -and $_.LocalPort -in $Ports } |
            Select-Object -ExpandProperty LocalPort -Unique |
            Sort-Object

        if (($listening -join ",") -eq (($Ports | Sort-Object) -join ",")) {
            return $true
        }
    }

    return $false
}

function Start-LobbyProxy {
    Start-Process -FilePath $powershellExe `
        -ArgumentList @(
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ('"{0}"' -f $lobbyProxyScript),
            "-MaxSessions",
            "4096",
            "-IdleTimeoutSeconds",
            "28800"
        ) `
        -WorkingDirectory $root | Out-Null
}

function Start-GameProxy {
    Start-Process -FilePath $powershellExe `
        -ArgumentList @(
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ('"{0}"' -f $gameProxyScript)
        ) `
        -WorkingDirectory $root | Out-Null
}

function Convert-ToTomlString {
    param([string]$Value)

    return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
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

function Normalize-ExtraClientArgs {
    param([string[]]$Args, [string]$Csv = "")

    $normalized = @()
    $allArgs = @($Args)
    if (-not [string]::IsNullOrWhiteSpace($Csv)) {
        $allArgs += ($Csv -split ";")
    }

    foreach ($arg in $allArgs) {
        if ([string]::IsNullOrWhiteSpace($arg)) {
            continue
        }

        foreach ($piece in ($arg -split ",")) {
            if (-not [string]::IsNullOrWhiteSpace($piece)) {
                $normalized += $piece.Trim()
            }
        }
    }

    return $normalized
}

function Stop-ExistingNetTestProcesses {
    $existingNetTestPids = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.ProcessId -ne $PID -and
                $null -ne $_.CommandLine -and
                (
                    $_.CommandLine -like "*tools\\launch-win64c-live.ps1*" -or
                    $_.CommandLine -like "*tools\\keep_local_live_stack.ps1*" -or
                    $_.CommandLine -like "*tools\\launch_lobby_tls_terminator.ps1*" -or
                    $_.CommandLine -like "*tools\\launch_game_tls_terminator.ps1*" -or
                    $_.CommandLine -like "*tools\\tcp_proxy.py*" -or
                    $_.CommandLine -like "*tools\\tls_terminate_proxy.py*" -or
                    $_.CommandLine -like "*OpenNXT.bat*run-server*" -or
                    $_.CommandLine -like "*com.opennxt.OpenNXT*"
                )
            } |
            Select-Object -ExpandProperty ProcessId -Unique
    )

    foreach ($processId in $existingNetTestPids) {
        try {
            taskkill /PID $processId /F | Out-Null
        } catch {}
    }
}

Stop-ExistingNetTestProcesses
Remove-Item $launchTrace -ErrorAction SilentlyContinue
Remove-Item $launchStateFile -ErrorAction SilentlyContinue
Write-LaunchTrace "starting launch-win64c-live"

Get-ListeningProcessIds -Ports @(443, 8081, 43595, 43596) |
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
if ($CaptureConsole) {
    Remove-Item $clientStdout, $clientStderr -ErrorAction SilentlyContinue
}
if ($EnableCefLogging -and (Test-Path $clientCefLog)) {
    Remove-Item $clientCefLog -Force -ErrorAction SilentlyContinue
}

$normalizedProxyUsernames = @()
$normalizedExtraClientArgs = Normalize-ExtraClientArgs -Args $ExtraClientArgs -Csv $ExtraClientArgsCsv
$openNxtBat = Join-Path $root "build\\install\\OpenNXT\\bin\\OpenNXT.bat"
$serverArgs = @("run-server")
$clientArgs = @($launchArg)
$proxyConfigExists = Test-Path $proxyConfigPath
$proxyConfigOriginalContent = if ($proxyConfigExists) { Get-Content $proxyConfigPath -Raw } else { $null }
$proxyConfigModified = $false

if ($CefRemoteDebuggingPort) {
    $clientArgs += "--remote-debugging-port=$CefRemoteDebuggingPort"
}

if ($EnableCefLogging) {
    $clientArgs += "--enable-logging"
    $clientArgs += "--log-severity=info"
    $clientArgs += "--log-file=$clientCefLog"
}

if ($normalizedExtraClientArgs.Count -gt 0) {
    $clientArgs += $normalizedExtraClientArgs
}

try {
    if ($EnableProxySupport) {
        $normalizedProxyUsernames = @(
            $ProxyUsernames |
                Where-Object { $null -ne $_ } |
                ForEach-Object { $_.Trim().ToLowerInvariant() } |
                Where-Object { $_ -ne "" } |
                Select-Object -Unique
        )

        if ($normalizedProxyUsernames.Count -eq 0) {
            throw "EnableProxySupport requires at least one username in -ProxyUsernames"
        }

        $proxyConfigLine = "usernames = [{0}]" -f (($normalizedProxyUsernames | ForEach-Object { Convert-ToTomlString $_ }) -join ", ")
        [System.IO.File]::WriteAllText($proxyConfigPath, $proxyConfigLine + [Environment]::NewLine)
        $proxyConfigModified = $true
        $serverArgs += "--enable-proxy-support"
    }

    $serverCommand = 'set "JAVA_TOOL_OPTIONS=-XX:TieredStopAtLevel=1" && "{0}" {1}' -f $openNxtBat, ($serverArgs -join " ")
    $wrapper = Start-Process -FilePath $env:ComSpec `
        -ArgumentList @("/c", $serverCommand) `
        -WorkingDirectory $root `
        -RedirectStandardOutput $serverOut `
        -RedirectStandardError $serverErr `
        -PassThru
    Write-LaunchTrace "started server wrapper pid=$($wrapper.Id)"

    $serverPid = $null
    if (-not (Wait-ListeningPorts -Ports @(8081, 43596) -TimeoutSeconds $StartupTimeoutSeconds)) {
        throw "Timed out waiting for OpenNXT server ports 8081 and 43596 after $StartupTimeoutSeconds seconds"
    }
    Write-LaunchTrace "server ports ready"

    $serverPid = Get-ListeningProcessIds -Ports @(8081, 43596) | Select-Object -First 1
    Write-LaunchTrace "server pid=$serverPid"
} finally {
    if ($proxyConfigModified) {
        if ($proxyConfigExists) {
            [System.IO.File]::WriteAllText($proxyConfigPath, $proxyConfigOriginalContent)
        } else {
            Remove-Item $proxyConfigPath -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-LaunchTrace "starting lobby proxy"
Start-LobbyProxy
Write-LaunchTrace "starting game proxy"
Start-GameProxy
Write-LaunchTrace "proxy launch scripts returned"

Remove-Item $watchdogOut, $watchdogErr -ErrorAction SilentlyContinue
$watchdog = Start-Process -FilePath $powershellExe `
    -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", ('"{0}"' -f $watchdogScript), "-CheckIntervalSeconds", "2") `
    -WorkingDirectory $root `
    -RedirectStandardOutput $watchdogOut `
    -RedirectStandardError $watchdogErr `
    -PassThru
Write-LaunchTrace "watchdog pid=$($watchdog.Id)"

if (-not (Wait-ListeningPorts -Ports @(443, 43595) -TimeoutSeconds $ProxyStartupTimeoutSeconds)) {
    throw "Timed out waiting for proxy ports 443 and 43595 after $ProxyStartupTimeoutSeconds seconds"
}
Write-LaunchTrace "proxy ports ready"

$lobbyProxyPid = Get-ListeningProcessIds -Ports @(443) | Select-Object -First 1
$gameProxyPid = Get-ListeningProcessIds -Ports @(43595) | Select-Object -First 1
Write-LaunchTrace "lobbyProxyPid=$lobbyProxyPid gameProxyPid=$gameProxyPid"

$clientStartArgs = @{
    FilePath = $clientExe
    ArgumentList = @($clientArgs | ForEach-Object { Quote-ProcessArgument $_ })
    WorkingDirectory = $clientDir
    PassThru = $true
}

if ($CaptureConsole) {
    $clientStartArgs.RedirectStandardOutput = $clientStdout
    $clientStartArgs.RedirectStandardError = $clientStderr
}

Write-LaunchTrace "starting client"
$client = Start-Process @clientStartArgs
Write-LaunchTrace "client pid=$($client.Id)"

$json = [pscustomobject]@{
    WrapperPid = $wrapper.Id
    ServerPid = $serverPid
    LobbyProxyPid = $lobbyProxyPid
    GameProxyPid = $gameProxyPid
    WatchdogPid = $watchdog.Id
    ClientPid = $client.Id
    ProxyMode = if ($EnableProxySupport) { "live-capture" } else { "local" }
    ProxyUsernames = $normalizedProxyUsernames
    ServerOut = $serverOut
    ServerErr = $serverErr
    WatchdogOut = $watchdogOut
    WatchdogErr = $watchdogErr
    ClientExe = $clientExe
    ClientArgs = $clientArgs
    ClientStdout = if ($CaptureConsole) { $clientStdout } else { $null }
    ClientStderr = if ($CaptureConsole) { $clientStderr } else { $null }
    ClientCefLog = if ($EnableCefLogging) { $clientCefLog } else { $null }
    LaunchStateFile = $launchStateFile
} | ConvertTo-Json -Depth 3
Set-Content -Path $launchStateFile -Value $json -Encoding ASCII
Write-Output $json
Write-LaunchTrace "launch-win64c-live completed"

exit 0
