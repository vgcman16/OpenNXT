param(
    [int]$DurationSeconds = 60,
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging,
    [switch]$UseOriginalClient,
    [switch]$DisableChecksumOverride,
    [switch]$BypassGameProxy,
    [string]$ConfigUrlOverride = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$programData = "C:\ProgramData\Jagex\RuneScape"
$localData = Join-Path $env:LOCALAPPDATA "Jagex\RuneScape"
$programBackup = "${programData}_BACKUP_$timestamp"
$localBackup = "${localData}_BACKUP_$timestamp"
$renamed = @()
$renameFailures = @()

Get-Process -Name "JagexLauncher", "rs2client", "RuneScape" -ErrorAction SilentlyContinue | ForEach-Object {
    taskkill /PID $_.Id /F | Out-Null
}

if (Test-Path $programData) {
    try {
        Rename-Item -Path $programData -NewName ([System.IO.Path]::GetFileName($programBackup))
        $renamed += [pscustomobject]@{ Original = $programData; Backup = $programBackup }
    } catch {
        $renameFailures += [pscustomobject]@{ Original = $programData; Error = $_.Exception.Message }
    }
}

if (Test-Path $localData) {
    try {
        Rename-Item -Path $localData -NewName ([System.IO.Path]::GetFileName($localBackup))
        $renamed += [pscustomobject]@{ Original = $localData; Backup = $localBackup }
    } catch {
        $renameFailures += [pscustomobject]@{ Original = $localData; Error = $_.Exception.Message }
    }
}

try {
    $launchArgs = @{
        StartupTimeoutSeconds = 90
        ProxyStartupTimeoutSeconds = 30
    }

    if ($UseOriginalClient) {
        $launchArgs.UseOriginalClient = $true
    }

    if ($DisableChecksumOverride) {
        $launchArgs.DisableChecksumOverride = $true
    }

    if ($BypassGameProxy) {
        $launchArgs.BypassGameProxy = $true
    }

    if (-not [string]::IsNullOrWhiteSpace($ConfigUrlOverride)) {
        $launchArgs.ConfigUrlOverride = $ConfigUrlOverride
    }

    $launchOutput = & (Join-Path $root "tools\launch-win64c-live.ps1") @launchArgs
    Start-Sleep -Seconds $DurationSeconds

    $launchStatePath = Join-Path $root "tmp-launch-win64c-live.state.json"
    $launchState = if (Test-Path $launchStatePath) {
        Get-Content -Path $launchStatePath -Raw | ConvertFrom-Json
    } else {
        $null
    }

    $clientAlive = $false
    if ($launchState -and $launchState.ClientPid) {
        $clientAlive = $null -ne (Get-Process -Id $launchState.ClientPid -ErrorAction SilentlyContinue)
    }

    $serverErr = Join-Path $root "tmp-manual-js5.err.log"
    $logTail = if (Test-Path $serverErr) { Get-Content -Path $serverErr | Select-Object -Last 120 } else { @() }

    [pscustomobject]@{
        Renamed = $renamed
        RenameFailures = $renameFailures
        LaunchOutput = ($launchOutput -join "`n")
        LaunchState = $launchState
        ClientAlive = $clientAlive
        LogTail = $logTail
    } | ConvertTo-Json -Depth 6
}
finally {
    $launchStatePath = Join-Path $root "tmp-launch-win64c-live.state.json"
    if (Test-Path $launchStatePath) {
        try {
            $launchState = Get-Content -Path $launchStatePath -Raw | ConvertFrom-Json
            foreach ($pid in @(
                $launchState.ClientPid,
                $launchState.GameProxyPid,
                $launchState.LobbyProxyPid,
                $launchState.WatchdogPid,
                $launchState.ServerPid,
                $launchState.WrapperPid
            )) {
                if ($pid) {
                    taskkill /PID $pid /F | Out-Null
                }
            }
        } catch {
        }
    }

    foreach ($entry in $renamed) {
        if (Test-Path $entry.Original) {
            Remove-Item -Path $entry.Original -Recurse -Force -ErrorAction SilentlyContinue
        }

        if (Test-Path $entry.Backup) {
            Rename-Item -Path $entry.Backup -NewName ([System.IO.Path]::GetFileName($entry.Original))
        }
    }
}
