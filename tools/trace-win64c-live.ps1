param(
    [int]$DurationSeconds = 20,
    [int]$PollMilliseconds = 250,
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging,
    [switch]$CaptureConsole,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$powershellExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$launchScript = Join-Path $PSScriptRoot "launch-win64c-live.ps1"
$outputDir = Join-Path $root "data\debug\client-boot-trace"
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$launchStateFile = Join-Path $root "tmp-launch-win64c-live.state.json"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$tracePath = Join-Path $outputDir ("live-trace-{0}.log" -f $stamp)
$launchStatePath = Join-Path $outputDir ("live-launch-{0}.json" -f $stamp)
$werSummaryPath = Join-Path $outputDir ("live-wer-{0}.json" -f $stamp)

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

function Get-NetstatUdpRecords {
    $records = @()

    foreach ($line in (netstat -ano -p udp)) {
        if ($line -notmatch '^\s*UDP\s+') {
            continue
        }

        $parts = ($line -replace '^\s+', '') -split '\s+'
        if ($parts.Length -lt 4) {
            continue
        }

        $localPort = Get-PortFromEndpoint $parts[1]
        if ($null -eq $localPort) {
            continue
        }

        $owningProcessId = 0
        if (-not [int]::TryParse($parts[3], [ref]$owningProcessId)) {
            continue
        }

        $records += [pscustomobject]@{
            LocalAddress  = $parts[1]
            LocalPort     = $localPort
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

function Get-TrackedClientProcesses {
    param($LaunchState)

    $processes = @(
        Get-CimInstance Win32_Process -Filter "Name = 'rs2client.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ProcessId -eq $LaunchState.ClientPid -or
                $_.ParentProcessId -eq $LaunchState.ClientPid -or
                ($LaunchState.ClientExe -and $_.ExecutablePath -eq $LaunchState.ClientExe)
            }
    )

    return @($processes | Sort-Object ProcessId -Unique)
}

function Get-LatestWerSummary {
    param(
        [datetime]$Since,
        [string]$ClientExe
    )

    $candidates = @(
        Get-ChildItem -Path "C:\ProgramData\Microsoft\Windows\WER\ReportArchive" -Directory -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -like "AppCrash_rs2client.exe*" -and
                $_.LastWriteTime -ge $Since.AddSeconds(-5)
            } |
            Sort-Object LastWriteTime -Descending
    )

    foreach ($dir in $candidates) {
        $reportPath = Join-Path $dir.FullName "Report.wer"
        try {
            $report = Get-Content -Path $reportPath -Raw -ErrorAction Stop
        } catch {
            continue
        }

        $appPath = if ($report -match '(?m)^AppPath=(.+)$') { $Matches[1].Trim() } else { "" }
        if ($ClientExe -and $appPath -and $appPath -ne $ClientExe) {
            continue
        }

        return [pscustomobject]@{
            ReportDirectory = $dir.FullName
            ReportPath = $reportPath
            LastWriteTime = $dir.LastWriteTime
            AppPath = $appPath
            ExceptionCode = if ($report -match '(?m)^Sig\[6\]\.Value=(.+)$') { $Matches[1].Trim() } else { $null }
            ExceptionOffset = if ($report -match '(?m)^Sig\[7\]\.Value=(.+)$') { $Matches[1].Trim() } else { $null }
            BucketId = if ($report -match '(?m)^Response\.BucketId=(.+)$') { $Matches[1].Trim() } else { $null }
        }
    }

    return $null
}

function Stop-TrackedProcesses {
    param($LaunchState = $null)

    $candidatePids = @()
    if ($null -ne $LaunchState) {
        $candidatePids = @(
            $LaunchState.ClientPid,
            $LaunchState.WatchdogPid,
            $LaunchState.GameProxyPid,
            $LaunchState.LobbyProxyPid,
            $LaunchState.ServerPid,
            $LaunchState.WrapperPid
        ) | Where-Object { $null -ne $_ } | Select-Object -Unique
    }

    foreach ($processId in $candidatePids) {
        try {
            taskkill /PID $processId /F | Out-Null
        } catch {
        }
    }

    Get-ListeningProcessIds -Ports @(443, 8081, 43595, 43596) |
        ForEach-Object {
            try {
                taskkill /PID $_ /F | Out-Null
            } catch {
            }
        }
}

$launch = $null

$launchCommand = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $launchScript
)

if ($CefRemoteDebuggingPort) {
    $launchCommand += @("-CefRemoteDebuggingPort", $CefRemoteDebuggingPort.ToString())
}
if ($EnableCefLogging) {
    $launchCommand += "-EnableCefLogging"
}
if ($CaptureConsole) {
    $launchCommand += "-CaptureConsole"
}

try {
    $traceStartedAt = Get-Date
    Remove-Item $launchStateFile -ErrorAction SilentlyContinue
    $launchOutput = & $powershellExe @launchCommand 2>&1
    if ($LASTEXITCODE -ne 0) {
        $launchText = ($launchOutput | Out-String).Trim()
        throw "launch-win64c-live.ps1 failed with exit code $LASTEXITCODE`n$launchText"
    }

    $launchJson = if (Test-Path $launchStateFile) {
        Get-Content -Path $launchStateFile -Raw
    } else {
        ($launchOutput | Out-String).Trim()
    }
    if ([string]::IsNullOrWhiteSpace($launchJson)) {
        throw "launch-win64c-live.ps1 produced no JSON output"
    }

    $launch = $launchJson | ConvertFrom-Json
    if (-not $launch.ClientPid) {
        throw "launch-win64c-live.ps1 returned no client pid`n$launchJson"
    }

    $launchJson | Set-Content -Path $launchStatePath -Encoding ASCII

    $clientPid = [int]$launch.ClientPid
    $deadline = (Get-Date).AddSeconds($DurationSeconds)

    "launch clientPid=$clientPid serverPid=$($launch.ServerPid) lobbyProxyPid=$($launch.LobbyProxyPid) gameProxyPid=$($launch.GameProxyPid) watchdogPid=$($launch.WatchdogPid)" | Set-Content -Path $tracePath -Encoding ASCII

    while ((Get-Date) -lt $deadline) {
        $timestamp = Get-Date -Format "HH:mm:ss.fff"
        $clientProcesses = @(Get-TrackedClientProcesses -LaunchState $launch)

        if ($clientProcesses.Count -eq 0) {
            Add-Content -Path $tracePath -Value "$timestamp process-exited"
            break
        }

        $clientPids = @($clientProcesses | Select-Object -ExpandProperty ProcessId -Unique)

        foreach ($clientProcess in $clientProcesses) {
            $liveProcess = Get-Process -Id $clientProcess.ProcessId -ErrorAction SilentlyContinue
            Add-Content -Path $tracePath -Value (
                "{0} process pid={1} parent={2} cpu={3} title={4} path={5}" -f
                    $timestamp,
                    $clientProcess.ProcessId,
                    $clientProcess.ParentProcessId,
                    (if ($liveProcess) { $liveProcess.CPU } else { "" }),
                    (if ($liveProcess) { $liveProcess.MainWindowTitle } else { "" }),
                    $clientProcess.ExecutablePath
            )
        }

        $connections = @(
            Get-NetstatTcpRecords |
                Where-Object { $_.OwningProcess -in $clientPids }
        )
        foreach ($connection in $connections) {
            Add-Content -Path $tracePath -Value (
                "{0} tcp pid={1} {2} -> {3} {4}" -f
                    $timestamp,
                    $connection.OwningProcess,
                    $connection.LocalAddress,
                    $connection.RemoteAddress,
                    $connection.State
            )
        }

        $udpEndpoints = @(
            Get-NetstatUdpRecords |
                Where-Object { $_.OwningProcess -in $clientPids }
        )
        foreach ($udpEndpoint in $udpEndpoints) {
            Add-Content -Path $tracePath -Value (
                "{0} udp pid={1} {2}" -f
                    $timestamp,
                    $udpEndpoint.OwningProcess,
                    $udpEndpoint.LocalAddress
            )
        }

        Start-Sleep -Milliseconds $PollMilliseconds
    }

    $werSummary = Get-LatestWerSummary -Since $traceStartedAt -ClientExe $launch.ClientExe
    if ($werSummary) {
        $werSummary | ConvertTo-Json -Depth 3 | Set-Content -Path $werSummaryPath -Encoding ASCII
        Add-Content -Path $tracePath -Value (
            "wer exceptionCode={0} exceptionOffset={1} bucket={2} report={3}" -f
                $werSummary.ExceptionCode,
                $werSummary.ExceptionOffset,
                $werSummary.BucketId,
                $werSummary.ReportPath
        )
    }

    if (-not $KeepRunning) {
        Stop-TrackedProcesses -LaunchState $launch
    }
} catch {
    if (-not $KeepRunning) {
        Stop-TrackedProcesses
    }
    throw
}

[pscustomobject]@{
    TracePath = $tracePath
    LaunchStatePath = $launchStatePath
    WerSummaryPath = if (Test-Path $werSummaryPath) { $werSummaryPath } else { $null }
    ClientPid = if ($launch) { [int]$launch.ClientPid } else { $null }
    KeepRunning = [bool]$KeepRunning
} | ConvertTo-Json -Depth 3
