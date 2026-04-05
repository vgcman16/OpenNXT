param(
    [switch]$EnableProxySupport,
    [string[]]$ProxyUsernames = @(),
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging,
    [switch]$CaptureConsole,
    [switch]$UsePatchedLauncher,
    [switch]$UseOriginalClient,
    [switch]$DisableChecksumOverride,
    [switch]$BypassGameProxy,
    [switch]$LobbyTlsPassthrough,
    [switch]$ForceLobbyTlsMitm,
    [switch]$DisableLobbyTlsPassthroughAuto,
    [string]$ContentTlsRemoteHost = "",
    [int]$ContentTlsRemotePort = 0,
    [switch]$ContentTlsRemoteRaw,
    [switch]$DisableWatchdog,
    [string]$DownloadMetadataSource = "",
    [string]$ConfigUrlOverride = "",
    [string[]]$ExtraClientArgs = @(),
    [string]$ExtraClientArgsCsv = "",
    [int]$StartupTimeoutSeconds = 90,
    [int]$ProxyStartupTimeoutSeconds = 30,
    [switch]$RepairRuntimeHotCache,
    [switch]$SkipRuntimeCacheSync,
    [switch]$AutoSwitchGraphicsCompat,
    [ValidateSet("auto", "true", "false", "default")]
    [string]$GraphicsCompatibilityMode = "auto",
    [ValidateSet("auto", "default", "power-saving", "high-performance")]
    [string]$GraphicsDevicePreference = "auto",
    [switch]$DisableUseAngle,
    [switch]$UseRuneScapeWrapper,
    [switch]$Force947StartupRouteRedirects,
    [switch]$Disable947InlineNullReadPatches,
    [switch]$Disable947JumpBypassGuards,
    [switch]$AllowRetailJs5Upstream
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$powershellExe = "$env:WINDIR\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
$serverOut = Join-Path $root "tmp-manual-js5.out.log"
$serverErr = Join-Path $root "tmp-manual-js5.err.log"
$lobbyProxyScript = Join-Path $PSScriptRoot "launch_lobby_tls_terminator.ps1"
$gameProxyScript = Join-Path $PSScriptRoot "launch_game_tls_terminator.ps1"
$watchdogScript = Join-Path $PSScriptRoot "keep_local_live_stack.ps1"
$setContentHostsOverrideScript = Join-Path $PSScriptRoot "set_content_hosts_override.ps1"
$clearContentHostsOverrideScript = Join-Path $PSScriptRoot "clear_content_hosts_override.ps1"
$watchdogOut = Join-Path $root "tmp-live-stack-watchdog.out.log"
$watchdogErr = Join-Path $root "tmp-live-stack-watchdog.err.log"
$certScript = Join-Path $PSScriptRoot "setup_lobby_tls_cert.ps1"
$tlsProxyScript = Join-Path $PSScriptRoot "tls_terminate_proxy.py"
$hostsFile = Join-Path $env:WINDIR "System32\\drivers\\etc\\hosts"
$launcherDir = Join-Path $root "data\\launchers\\win"
$launcherExe = Join-Path $launcherDir "patched.exe"
$launchArg = "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0&baseConfigSource=live&liveCache=1&downloadMetadataSource=original"
$tlsPassthroughConfigHost = "content.runescape.com"
$proxyConfigPath = Join-Path $root "data\\config\\proxy.toml"
$serverConfigPath = Join-Path $root "data\\config\\server.toml"
$clientStdout = Join-Path $root "tmp-rs2client.stdout.log"
$clientStderr = Join-Path $root "tmp-rs2client.stderr.log"
$clientCefLog = Join-Path $root "tmp-rs2client-cef.log"
$directPatchTool = Join-Path $PSScriptRoot "launch_rs2client_direct_patch.py"
$wrapperRewriteTool = Join-Path $PSScriptRoot "launch_runescape_wrapper_rewrite.py"
$graphicsDialogHelper = Join-Path $PSScriptRoot "invoke_runescape_graphics_dialog_action.ps1"
$launcherPreferencesScript = Join-Path $PSScriptRoot "set_runescape_launcher_preferences.ps1"
$graphicsDeviceResolverScript = Join-Path $PSScriptRoot "resolve_runescape_graphics_device.ps1"
$windowsGpuPreferenceScript = Join-Path $PSScriptRoot "set_windows_gpu_preference.ps1"
$runtimeCacheSyncScript = Join-Path $PSScriptRoot "sync_runescape_runtime_cache.ps1"
$runtimeHotCacheRepairScript = Join-Path $PSScriptRoot "repair_runescape_runtime_hot_cache.ps1"
$installedRuntimeSyncTool = Join-Path $PSScriptRoot "sync_runescape_installed_runtime.py"
$directPatchTrace = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-live.jsonl"
$directPatchSummary = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-live.json"
$directPatchStdout = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-live.stdout.log"
$directPatchStderr = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-live.stderr.log"
$directPatchStartupHookOutput = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-live-hook.jsonl"
$wrapperRewriteTrace = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live.jsonl"
$wrapperRewriteSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live.json"
$wrapperRewriteChildHookOutput = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-child-hook.jsonl"
$wrapperRewriteStdout = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live.stdout.log"
$wrapperRewriteStderr = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live.stderr.log"
$graphicsDialogSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-graphics-dialog.json"
$launcherPreferencesSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-launcher-preferences.json"
$graphicsDeviceSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-graphics-device.json"
$gpuPreferenceSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-gpu-preference.json"
$runtimeCacheSyncSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-runtime-cache-sync.json"
$runtimeHotCacheRepairSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-runtime-hot-cache-repair.json"
$installedRuntimeSyncSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-installed-runtime-sync.json"
$installedRuntimePostLaunchVerifySummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-installed-runtime-post-launch-check.json"
$directPatchResourceGateOutputRoot = Join-Path $root "data\\debug\\application-resource-gate-947-direct-helper-live"
$rsaConfigPath = Join-Path $root "data\\config\\rsa.toml"
$launchTrace = Join-Path $root "tmp-launch-win64c-live.trace.log"
$launchStateFile = Join-Path $root "tmp-launch-win64c-live.state.json"
$startupConfigSnapshotPath = Join-Path $root "tmp-947-startup-config.ws"
$startupConfigSnapshotReady = $false
$lobbyProxyOut = Join-Path $root "tmp-lobby-tls-terminator.out.log"
$lobbyProxyErr = Join-Path $root "tmp-lobby-tls-terminator.err.log"
$lobbyProxyOutputDir = Join-Path $root "data\\debug\\lobby-tls-terminator"
$defaultMitmPrimaryHost = "localhost"
$installedGameWrapperExe = if ([string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
    $null
} else {
    Join-Path ${env:ProgramFiles(x86)} "Jagex Launcher\\Games\\RuneScape\\RuneScape.exe"
}
$installedGameClientExe = if ([string]::IsNullOrWhiteSpace($env:ProgramData)) {
    $null
} else {
    Join-Path $env:ProgramData "Jagex\\launcher\\rs2client.exe"
}
$runtimeHotArchiveIds947 = @(2,3,8,12,13,16,17,18,19,20,21,22,24,26,27,28,29,49,57,58,59,60,61,62,65,66)

function Get-ConfiguredBuild {
    param(
        [string]$Path,
        [int]$DefaultValue = 947
    )

    if (-not (Test-Path $Path)) {
        return $DefaultValue
    }

    foreach ($line in (Get-Content $Path)) {
        if ($line -match '^\s*build\s*=\s*(\d+)') {
            return [int]$Matches[1]
        }
    }

    return $DefaultValue
}

$configuredClientBuild = Get-ConfiguredBuild -Path $serverConfigPath
$clientDir = Join-Path $root ("data\\clients\\{0}\\win64c\\patched" -f $configuredClientBuild)
$clientExe = Join-Path $clientDir "rs2client.exe"
$originalClientDir = Join-Path $root ("data\\clients\\{0}\\win64c\\original" -f $configuredClientBuild)
$originalClientExe = Join-Path $root ("data\\clients\\{0}\\win64c\\original\\rs2client.exe" -f $configuredClientBuild)

function Write-LaunchTrace {
    param([string]$Message)

    Add-Content -Path $launchTrace -Value ("{0} {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $Message)
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

function Sync-InstalledRuneScapeRuntimeFile {
    param(
        [string]$SourcePath,
        [string]$ClientDirectory,
        [string]$FileName
    )

    if (
        [string]::IsNullOrWhiteSpace($SourcePath) -or
        [string]::IsNullOrWhiteSpace($ClientDirectory) -or
        [string]::IsNullOrWhiteSpace($FileName) -or
        -not (Test-Path $ClientDirectory) -or
        -not (Test-Path $SourcePath)
    ) {
        return $null
    }

    $destination = Join-Path $ClientDirectory $FileName
    $shouldCopy = -not (Test-Path $destination)
    if (-not $shouldCopy) {
        $sourceItem = Get-Item $SourcePath
        $destinationItem = Get-Item $destination
        $shouldCopy = $sourceItem.Length -ne $destinationItem.Length -or
            $sourceItem.LastWriteTimeUtc -gt $destinationItem.LastWriteTimeUtc
    }

    if ($shouldCopy) {
        Copy-Item $SourcePath $destination -Force
        Write-LaunchTrace ("staged {0} from {1} to {2}" -f $FileName, $SourcePath, $destination)
    }

    return $destination
}

function Sync-InstalledRuneScapeWrapper {
    param([string]$ClientDirectory)

    if ([string]::IsNullOrWhiteSpace($ClientDirectory) -or -not (Test-Path $ClientDirectory)) {
        return $null
    }

    # Keep the downloader-produced rs2client.exe intact. The 947 wrapper manifest validates the
    # staged client binary by CRC, and overwriting it with the launcher-installed runtime can strand
    # the splash screen on "Loading application resources" before the child ever starts.
    $wrapperDestination = Sync-InstalledRuneScapeRuntimeFile -SourcePath $installedGameWrapperExe -ClientDirectory $ClientDirectory -FileName "RuneScape.exe"

    return $wrapperDestination
}

function Resolve-MainClientProcess {
    param(
        [int]$BootstrapPid,
        [int]$TimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds([Math]::Max(0, $TimeoutSeconds))
    do {
        $directClientPid = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -eq "rs2client.exe" -and
                (
                    [string]::IsNullOrWhiteSpace($_.CommandLine) -or
                    $_.CommandLine -notlike "*--compileshader*"
                )
            } |
            Sort-Object CreationDate -Descending |
            Select-Object -ExpandProperty ProcessId -First 1
        $directClient = if ($directClientPid) {
            Get-Process -Id $directClientPid -ErrorAction SilentlyContinue
        } else {
            $null
        }
        if ($null -ne $directClient) {
            return $directClient
        }

        $bootstrap = Get-Process -Id $BootstrapPid -ErrorAction SilentlyContinue
        if ($null -eq $bootstrap) {
            break
        }

        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return Get-Process -Id $BootstrapPid -ErrorAction SilentlyContinue
}

function Resolve-WrapperClientProcess {
    param(
        [int]$WrapperPid,
        [int]$ChildPid,
        [int]$TimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds([Math]::Max(0, $TimeoutSeconds))
    do {
        if ($ChildPid -gt 0) {
            $directChild = Get-Process -Id $ChildPid -ErrorAction SilentlyContinue
            if ($null -ne $directChild) {
                return $directChild
            }
        }

        $childCandidatePid = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ParentProcessId -eq $WrapperPid -and
                $_.Name -eq "rs2client.exe" -and
                (
                    [string]::IsNullOrWhiteSpace($_.CommandLine) -or
                    $_.CommandLine -notlike "*--compileshader*"
                )
            } |
            Sort-Object CreationDate -Descending |
            Select-Object -ExpandProperty ProcessId -First 1
        if ($childCandidatePid) {
            $childCandidate = Get-Process -Id $childCandidatePid -ErrorAction SilentlyContinue
            if ($null -ne $childCandidate) {
                return $childCandidate
            }
        }

        $fallbackClient = Resolve-MainClientProcess -BootstrapPid $WrapperPid -TimeoutSeconds 0
        if ($null -ne $fallbackClient) {
            return $fallbackClient
        }

        $wrapper = Get-Process -Id $WrapperPid -ErrorAction SilentlyContinue
        if ($null -eq $wrapper) {
            break
        }

        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return $null
}

if (-not ("OpenNxt.CommandLineNative" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace OpenNxt {
    public static class CommandLineNative {
        [DllImport("shell32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
        public static extern IntPtr CommandLineToArgvW(string lpCmdLine, out int pNumArgs);

        [DllImport("kernel32.dll", SetLastError=true)]
        public static extern IntPtr LocalFree(IntPtr hMem);
    }
}
"@
}

function Split-WindowsCommandLine {
    param([string]$CommandLine)

    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return @()
    }

    $argc = 0
    $argvPtr = [OpenNxt.CommandLineNative]::CommandLineToArgvW($CommandLine, [ref]$argc)
    if ($argvPtr -eq [IntPtr]::Zero -or $argc -le 0) {
        return @($CommandLine)
    }

    try {
        $arguments = New-Object string[] $argc
        for ($index = 0; $index -lt $argc; $index++) {
            $entryPtr = [System.Runtime.InteropServices.Marshal]::ReadIntPtr($argvPtr, $index * [IntPtr]::Size)
            $arguments[$index] = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($entryPtr)
        }
        return $arguments
    } finally {
        [void][OpenNxt.CommandLineNative]::LocalFree($argvPtr)
    }
}

function Resolve-WrapperFallbackClientArgs {
    param(
        [string]$WrapperChildCommandLine,
        [string]$LaunchArg
    )

    $tokenizedArgs = @(Split-WindowsCommandLine -CommandLine $WrapperChildCommandLine)
    if ($tokenizedArgs.Count -le 1) {
        return @($LaunchArg)
    }

    return @($tokenizedArgs | Select-Object -Skip 1)
}

function Invoke-DirectPatchedLiveLaunch {
    param(
        [string]$ClientExePath,
        [string]$WorkingDirectory,
        [string[]]$ClientArgumentList,
        [string]$SummaryPath,
        [string]$TracePath,
        [string]$StartupHookOutputPath,
        [string]$DirectPatchToolPath,
        [string]$WorkspaceRoot,
        [string]$RsaConfigPath,
        [int]$MonitorSeconds,
        [string[]]$InlinePatchOffsets = @(),
        [string[]]$JumpBypassSpecs = @(),
        [string[]]$DirectPatchExtraArgs = @(),
        [string[]]$RedirectSpecs = @()
    )

    if (Test-Path $SummaryPath) {
        Remove-Item $SummaryPath -Force -ErrorAction SilentlyContinue
    }
    if (-not [string]::IsNullOrWhiteSpace($StartupHookOutputPath) -and (Test-Path $StartupHookOutputPath)) {
        Remove-Item $StartupHookOutputPath -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $directPatchStdout, $directPatchStderr -Force -ErrorAction SilentlyContinue

    function Read-DirectPatchSummary {
        param([string]$Path)

        $lastError = $null
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            try {
                $rawSummary = Get-Content -Path $Path -Raw -ErrorAction Stop
                if (-not [string]::IsNullOrWhiteSpace($rawSummary)) {
                    return $rawSummary | ConvertFrom-Json -ErrorAction Stop
                }
            } catch {
                $lastError = $_
            }

            Start-Sleep -Milliseconds 250
        }

        if ($lastError) {
            throw "Direct rs2client patch launch summary could not be parsed: $Path. $($lastError.Exception.Message)"
        }

        throw "Direct rs2client patch launch summary was empty: $Path"
    }

    function Stop-DirectPatchAttemptArtifacts {
        param(
            [System.Diagnostics.Process]$HelperProcess,
            [string]$LaunchedClientPath
        )

        $targetPids = @()
        if ($HelperProcess) {
            $targetPids += $HelperProcess.Id
        }

        if (-not [string]::IsNullOrWhiteSpace($LaunchedClientPath) -and (Test-Path $LaunchedClientPath)) {
            $resolvedClientPath = [System.IO.Path]::GetFullPath($LaunchedClientPath)
            $targetPids += @(
                Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                    Where-Object {
                        $_.ProcessId -ne $PID -and
                        $null -ne $_.ExecutablePath -and
                        [string]::Equals([System.IO.Path]::GetFullPath($_.ExecutablePath), $resolvedClientPath, [System.StringComparison]::OrdinalIgnoreCase)
                    } |
                    Select-Object -ExpandProperty ProcessId -Unique
            )
        }

        $targetPids = @(
            $targetPids |
                Where-Object { $_ -and $_ -ne $PID } |
                Sort-Object -Unique
        )
        foreach ($processId in $targetPids) {
            try {
                taskkill /PID $processId /T /F | Out-Null
            } catch {}
        }

        return $targetPids
    }

    $directPatchArgs = @(
        $DirectPatchToolPath,
        "--client-exe",
        $ClientExePath,
        "--working-dir",
        $WorkingDirectory,
        "--summary-output",
        $SummaryPath,
        "--trace-output",
        $TracePath,
        "--monitor-seconds",
        ([string]([Math]::Max(15, $MonitorSeconds)))
    )
    if (-not [string]::IsNullOrWhiteSpace($StartupHookOutputPath)) {
        $directPatchArgs += "--startup-hook-output"
        $directPatchArgs += $StartupHookOutputPath
    }
    if (-not [string]::IsNullOrWhiteSpace($RsaConfigPath) -and (Test-Path $RsaConfigPath)) {
        $directPatchArgs += "--rsa-config"
        $directPatchArgs += $RsaConfigPath
        if ($configuredClientBuild -ge 947 -and (Test-Path $originalClientExe)) {
            $directPatchArgs += "--js5-rsa-source-exe"
            $directPatchArgs += $originalClientExe
        }
    }
    foreach ($clientArg in $ClientArgumentList) {
        $directPatchArgs += "--client-arg"
        $directPatchArgs += $clientArg
    }
    foreach ($inlinePatchOffset in $InlinePatchOffsets) {
        $directPatchArgs += "--patch-inline-offset"
        $directPatchArgs += $inlinePatchOffset
    }
    foreach ($jumpBypassSpec in $JumpBypassSpecs) {
        $directPatchArgs += "--patch-jump-bypass"
        $directPatchArgs += $jumpBypassSpec
    }
    foreach ($directPatchExtraArg in $DirectPatchExtraArgs) {
        $directPatchArgs += $directPatchExtraArg
    }
    foreach ($redirectSpec in $RedirectSpecs) {
        $directPatchArgs += "--resolve-redirect"
        $directPatchArgs += $redirectSpec
    }

    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    $quotedDirectPatchArgs = @($directPatchArgs | ForEach-Object { Quote-ProcessArgument $_ })
    Write-LaunchTrace ("direct patch helper start exe={0}" -f $ClientExePath)
    $directPatchHelper = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $quotedDirectPatchArgs `
        -WorkingDirectory $WorkspaceRoot `
        -RedirectStandardOutput $directPatchStdout `
        -RedirectStandardError $directPatchStderr `
        -PassThru
    Write-LaunchTrace ("direct patch helper pid={0}" -f $directPatchHelper.Id)
    $summaryDeadline = (Get-Date).AddSeconds([Math]::Max(15, $MonitorSeconds))
    while ((Get-Date) -lt $summaryDeadline -and -not (Test-Path $SummaryPath)) {
        $helperStillRunning = Get-Process -Id $directPatchHelper.Id -ErrorAction SilentlyContinue
        if ($null -eq $helperStillRunning) {
            break
        }

        Start-Sleep -Milliseconds 500
    }

    if (-not (Test-Path $SummaryPath)) {
        $directPatchExitCode = $null
        try {
            $directPatchHelper.Refresh()
            if ($directPatchHelper.HasExited) {
                $directPatchExitCode = $directPatchHelper.ExitCode
            }
        } catch {}
        Write-LaunchTrace ("direct patch helper summary missing helperPid={0} exitCode={1}" -f $directPatchHelper.Id, $(if ($null -ne $directPatchExitCode) { $directPatchExitCode } else { "running" }))
        if (Test-Path $directPatchStderr) {
            $stderrTail = (Get-Content -Path $directPatchStderr -ErrorAction SilentlyContinue | Select-Object -Last 20) -join " | "
            if (-not [string]::IsNullOrWhiteSpace($stderrTail)) {
                Write-LaunchTrace ("direct patch helper stderr tail={0}" -f $stderrTail)
            }
        }
        $terminatedPids = @(Stop-DirectPatchAttemptArtifacts -HelperProcess $directPatchHelper -LaunchedClientPath $ClientExePath)
        if ($terminatedPids.Count -gt 0) {
            Write-LaunchTrace ("direct patch helper cleanup pids={0}" -f ($terminatedPids -join ","))
        }
        if ($null -ne $directPatchExitCode) {
            throw "Direct rs2client patch launch failed with exit code $directPatchExitCode."
        }
        throw "Direct rs2client patch launch completed without a summary output: $SummaryPath"
    }

    Write-LaunchTrace ("direct patch helper summary ready helperPid={0}" -f $directPatchHelper.Id)
    $directPatchLaunchSummary = Read-DirectPatchSummary -Path $SummaryPath
    $summaryStage = if ($directPatchLaunchSummary.PSObject.Properties.Name -contains "summaryStage") {
        [string]$directPatchLaunchSummary.summaryStage
    } else {
        "unknown"
    }
    Write-LaunchTrace ("direct patch helper summary loaded helperPid={0} pid={1} stage={2}" -f $directPatchHelper.Id, $directPatchLaunchSummary.pid, $summaryStage)
    $resolvedClientPid = [int]$directPatchLaunchSummary.pid
    $client = $null
    $resolveDeadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $resolveDeadline -and $null -eq $client) {
        $client = Get-Process -Id $resolvedClientPid -ErrorAction SilentlyContinue
        if ($null -eq $client -and [bool]$directPatchLaunchSummary.processAlive) {
            $client = Resolve-MainClientProcess -BootstrapPid $resolvedClientPid -TimeoutSeconds 2
        }
        if ($null -eq $client) {
            Start-Sleep -Milliseconds 250
        }
    }
    if ($null -eq $client) {
        Write-LaunchTrace ("direct patch helper client resolution failed helperPid={0} pid={1}" -f $directPatchHelper.Id, $resolvedClientPid)
        $terminatedPids = @(Stop-DirectPatchAttemptArtifacts -HelperProcess $directPatchHelper -LaunchedClientPath $ClientExePath)
        if ($terminatedPids.Count -gt 0) {
            Write-LaunchTrace ("direct patch helper cleanup pids={0}" -f ($terminatedPids -join ","))
        }
        throw "Direct rs2client patch launch completed but no live client process could be resolved."
    }
    Write-LaunchTrace ("direct patch helper client resolved helperPid={0} pid={1}" -f $directPatchHelper.Id, $client.Id)

    return [pscustomobject]@{
        Summary = $directPatchLaunchSummary
        BootstrapClient = [pscustomobject]@{ Id = $resolvedClientPid }
        Client = $client
        ResolvedClientPid = $resolvedClientPid
        HelperProcess = $directPatchHelper
    }
}

function Invoke-WrapperFallbackToDirectPatchedLive {
    param(
        [string]$Reason,
        [string]$WrapperExePath,
        [string]$FallbackClientExePath,
        [string]$WorkingDirectory,
        [string]$LaunchArg,
        [string[]]$FallbackClientArgs = @(),
        [string]$SummaryPath,
        [string]$TracePath,
        [string]$StartupHookOutputPath,
        [string]$DirectPatchToolPath,
        [string]$WorkspaceRoot,
        [string]$RsaConfigPath,
        [int]$MonitorSeconds,
        [string[]]$InlinePatchOffsets = @(),
        [string[]]$JumpBypassSpecs = @(),
        [string[]]$DirectPatchExtraArgs = @(),
        [string[]]$RedirectSpecs = @()
    )

    Write-LaunchTrace ("wrapper fallback to direct reason={0}" -f $Reason)
    Stop-WrapperLaunchArtifacts -WrapperExePath $WrapperExePath | Out-Null

    $effectiveFallbackClientArgs = if ($FallbackClientArgs.Count -gt 0) {
        $FallbackClientArgs
    } else {
        @($LaunchArg)
    }

    $launch = Invoke-DirectPatchedLiveLaunch `
        -ClientExePath $FallbackClientExePath `
        -WorkingDirectory $WorkingDirectory `
        -ClientArgumentList $effectiveFallbackClientArgs `
        -SummaryPath $SummaryPath `
        -TracePath $TracePath `
        -StartupHookOutputPath $StartupHookOutputPath `
        -DirectPatchToolPath $DirectPatchToolPath `
        -WorkspaceRoot $WorkspaceRoot `
        -RsaConfigPath $RsaConfigPath `
        -MonitorSeconds $MonitorSeconds `
        -InlinePatchOffsets $InlinePatchOffsets `
        -JumpBypassSpecs $JumpBypassSpecs `
        -DirectPatchExtraArgs $DirectPatchExtraArgs `
        -RedirectSpecs $RedirectSpecs

    return [pscustomobject]@{
        Reason = $Reason
        Launch = $launch
    }
}

function Get-NewestWriteTimeUtc {
    param([string[]]$Paths)

    $newest = [datetime]::MinValue
    foreach ($path in $Paths) {
        if (-not (Test-Path $path)) {
            continue
        }

        $item = Get-Item $path
        if ($item.PSIsContainer) {
            $candidate = Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTimeUtc -Descending |
                Select-Object -First 1
            if ($null -ne $candidate -and $candidate.LastWriteTimeUtc -gt $newest) {
                $newest = $candidate.LastWriteTimeUtc
            }
        } elseif ($item.LastWriteTimeUtc -gt $newest) {
            $newest = $item.LastWriteTimeUtc
        }
    }

    return $newest
}

function Ensure-InstalledServerCurrent {
    $installBin = Join-Path $root "build\\install\\OpenNXT\\bin\\OpenNXT.bat"
    $installLibDir = Join-Path $root "build\\install\\OpenNXT\\lib"
    $installedJar = Get-ChildItem $installLibDir -Filter "OpenNXT-*.jar" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "sources|javadoc" } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    $sourceRoots = @(
        (Join-Path $root "build.gradle"),
        (Join-Path $root "gradle.properties"),
        (Join-Path $root "src\\main"),
        (Join-Path $root "src\\generated"),
        (Join-Path $root "src\\main\\resources")
    )
    $newestSourceTime = Get-NewestWriteTimeUtc -Paths $sourceRoots
    $installedTime = if ($null -ne $installedJar) { $installedJar.LastWriteTimeUtc } else { [datetime]::MinValue }
    $needsInstallDist = -not (Test-Path $installBin) -or $null -eq $installedJar -or $newestSourceTime -gt $installedTime

    if (-not $needsInstallDist) {
        Write-LaunchTrace ("installDist up-to-date source={0:o} installed={1:o}" -f $newestSourceTime, $installedTime)
        return
    }

    Write-LaunchTrace ("installDist refresh=start source={0:o} installed={1:o}" -f $newestSourceTime, $installedTime)
    & (Join-Path $root "gradlew.bat") --no-daemon --console=plain installDist
    if ($LASTEXITCODE -ne 0) {
        throw "installDist failed while preparing the live stack."
    }

    $refreshedJar = Get-ChildItem $installLibDir -Filter "OpenNXT-*.jar" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "sources|javadoc" } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not (Test-Path $installBin) -or $null -eq $refreshedJar) {
        throw "installDist completed but the installed server artifacts are still missing."
    }

    Write-LaunchTrace ("installDist refresh=done installed={0:o}" -f $refreshedJar.LastWriteTimeUtc)
}

function Get-InstalledServerJar {
    $installLibDir = Join-Path $root "build\\install\\OpenNXT\\lib"
    return Get-ChildItem $installLibDir -Filter "OpenNXT-*.jar" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "sources|javadoc" } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
}

function Test-InstalledServerEntrypoint {
    $installedJar = Get-InstalledServerJar
    if ($null -eq $installedJar) {
        return $false
    }

    try {
        $entries = & jar tf $installedJar.FullName 2>$null
        return ($entries | Select-String -SimpleMatch "com/opennxt/MainKt.class") -ne $null
    } catch {
        return $false
    }
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

function Get-TcpListenerRecords {
    param([int[]]$Ports)

    $normalizedPorts = @(
        $Ports |
            Where-Object { $_ -is [int] -and $_ -gt 0 } |
            Select-Object -Unique
    )
    if ($normalizedPorts.Count -eq 0) {
        return @()
    }

    try {
        $tcpRows = @(
            Get-NetTCPConnection -State Listen -ErrorAction Stop |
                Where-Object { $_.LocalPort -in $normalizedPorts }
        )
        return @(
            $tcpRows |
                ForEach-Object {
                    [pscustomobject]@{
                        LocalAddress  = [string]$_.LocalAddress
                        LocalPort     = [int]$_.LocalPort
                        RemoteAddress = [string]$_.RemoteAddress
                        RemotePort    = if ($null -ne $_.RemotePort) { [int]$_.RemotePort } else { $null }
                        State         = [string]$_.State
                        OwningProcess = [int]$_.OwningProcess
                        Source        = "Get-NetTCPConnection"
                    }
                }
        )
    } catch {
        return @(
            Get-NetstatTcpRecords |
                Where-Object { $_.State -eq "LISTENING" -and $_.LocalPort -in $normalizedPorts } |
                ForEach-Object {
                    [pscustomobject]@{
                        LocalAddress  = $_.LocalAddress
                        LocalPort     = $_.LocalPort
                        RemoteAddress = $_.RemoteAddress
                        RemotePort    = $_.RemotePort
                        State         = $_.State
                        OwningProcess = $_.OwningProcess
                        Source        = "netstat"
                    }
                }
        )
    }
}

function Get-ListeningPortSnapshot {
    param([int[]]$Ports)

    $records = @(
        Get-TcpListenerRecords -Ports $Ports |
            Sort-Object LocalPort, OwningProcess, LocalAddress, Source
    )
    if ($records.Count -eq 0) {
        return "<none>"
    }

    return ($records | ForEach-Object {
        "{0}@{1}/pid={2}/src={3}" -f $_.LocalPort, $_.LocalAddress, $_.OwningProcess, $_.Source
    }) -join "; "
}

function Get-ProcessStateSummary {
    param([Nullable[int]]$Pid)

    if ($null -eq $Pid -or $Pid -le 0) {
        return "<none>"
    }

    $process = Get-Process -Id $Pid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return "pid=$Pid alive=false"
    }

    return "pid=$($process.Id) alive=true name=$($process.ProcessName)"
}

function Write-ServerStartupDiagnostics {
    param(
        $WrapperProcess,
        [int[]]$Ports,
        [string]$Prefix = "server-startup-diagnostics",
        [int]$TailLines = 40
    )

    $wrapperSummary = if ($null -ne $WrapperProcess) {
        Get-ProcessStateSummary -Pid $WrapperProcess.Id
    } else {
        "<null-wrapper>"
    }
    Write-LaunchTrace ("{0} wrapper={1}" -f $Prefix, $wrapperSummary)
    Write-LaunchTrace ("{0} listenerSnapshot={1}" -f $Prefix, (Get-ListeningPortSnapshot -Ports $Ports))

    $stderrTail = if (Test-Path $serverErr) {
        @(
            Get-Content $serverErr -Tail $TailLines -ErrorAction SilentlyContinue
        )
    } else {
        @()
    }
    $stderrSummary = if ($stderrTail.Count -gt 0) {
        ($stderrTail -join " <NL> ")
    } elseif (Test-Path $serverErr) {
        "<empty>"
    } else {
        "<missing>"
    }
    Write-LaunchTrace ("{0} stderrTail={1}" -f $Prefix, $stderrSummary)
}

function Get-ListeningProcessIds {
    param([int[]]$Ports)

    return @(
        Get-TcpListenerRecords -Ports $Ports |
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
    $requiredPorts = @(
        $Ports |
            Where-Object { $_ -is [int] -and $_ -gt 0 } |
            Select-Object -Unique
    )
    if ($requiredPorts.Count -eq 0) {
        return $true
    }

    for ($i = 0; $i -lt $retries; $i++) {
        if ($i -gt 0) {
            Start-Sleep -Milliseconds $DelayMilliseconds
        }

        $listening = @()
        try {
            $listening = @(
                Get-TcpListenerRecords -Ports $requiredPorts |
                    ForEach-Object { [int]$_.LocalPort } |
                    Select-Object -Unique |
                    Sort-Object
            )
        } catch {
            if (Get-Command Write-LaunchTrace -ErrorAction SilentlyContinue) {
                Write-LaunchTrace (
                    "wait-listening-ports query exception attempt={0} ports={1} message={2}" -f
                        ($i + 1),
                        ($requiredPorts -join ","),
                        $_.Exception.Message
                )
            }
            $listening = @()
        }

        $allPresent = $true
        foreach ($requiredPort in $requiredPorts) {
            if (-not ($listening -contains [int]$requiredPort)) {
                $allPresent = $false
                break
            }
        }

        if ($allPresent) {
            return $true
        }
    }

    return $false
}

function Start-LobbyProxy {
    if ($null -eq $script:CanonicalMitmTrustState) {
        throw "Canonical MITM trust must be initialized before starting the lobby proxy."
    }

    $rawRemoteHost = "127.0.0.1"
    # The local :443 multiplexer must send raw pre-login bytes directly to the
    # internal backend port. The old working login path used 43596 here, not the
    # public game TLS port on 43594.
    $rawRemotePort = if ($configuredGameBackendPort -gt 0) { $configuredGameBackendPort } else { $configuredGamePort }
    $effectiveContentTlsRemoteHost = $ContentTlsRemoteHost
    $effectiveContentTlsRemotePort = $ContentTlsRemotePort
    $effectiveContentTlsConnectHost = ""
    $effectiveContentTlsConnectPort = 0
    $effectiveContentTlsRemoteRaw = $ContentTlsRemoteRaw.IsPresent

    if (
        $script:UseContentTlsRoute -and
        -not $script:UseLobbyTlsPassthroughProxy -and
        [string]::IsNullOrWhiteSpace($effectiveContentTlsRemoteHost) -and
        $effectiveContentTlsRemotePort -le 0
    ) {
        $effectiveContentTlsRemoteHost = "content.runescape.com"
        $effectiveContentTlsRemotePort = 443
        $effectiveContentTlsConnectHost = "127.0.0.1"
        $effectiveContentTlsConnectPort = $configuredHttpPort
        $effectiveContentTlsRemoteRaw = $true
    }

    $script:EffectiveContentTlsRemoteHost = $effectiveContentTlsRemoteHost
    $script:EffectiveContentTlsRemotePort = $effectiveContentTlsRemotePort
    $script:EffectiveContentTlsConnectHost = $effectiveContentTlsConnectHost
    $script:EffectiveContentTlsConnectPort = $effectiveContentTlsConnectPort
    $script:EffectiveContentTlsRemoteRaw = $effectiveContentTlsRemoteRaw
    $extraTlsMitmHosts = @($script:ConfiguredTlsExtraMitmHosts)

    $lobbyProxyArgs = @(
        "-ListenHost",
        "127.0.0.1,::1",
        "-RemoteHost",
        $rawRemoteHost,
        "-RemotePort",
        $rawRemotePort.ToString(),
        "-SecureGamePassthroughHost",
        "127.0.0.1",
        "-SecureGamePassthroughPort",
        $configuredGamePort.ToString(),
        "-SecureGameDecryptedHost",
        "127.0.0.1",
        "-SecureGameDecryptedPort",
        $configuredGameBackendPort.ToString(),
        "-LobbyHost",
        $script:ConfiguredMitmLobbyHost,
        "-MaxSessions",
        "0",
        "-IdleTimeoutSeconds",
        "0"
    )
    if ($extraTlsMitmHosts.Count -gt 0) {
        $lobbyProxyArgs += @(
            "-TlsExtraMitmHost",
            ($extraTlsMitmHosts -join ",")
        )
    }
    if ($AllowRetailJs5Upstream) {
        $lobbyProxyArgs += "-AllowRetailJs5Upstream"
    }

    if ($script:UseContentTlsRoute) {
        if ($script:UseLobbyTlsPassthroughProxy) {
            $lobbyProxyArgs += "-TlsPassthrough"
        } elseif (-not [string]::IsNullOrWhiteSpace($effectiveContentTlsRemoteHost) -and $effectiveContentTlsRemotePort -gt 0) {
            $lobbyProxyArgs += @(
                "-TlsRemoteHost",
                $effectiveContentTlsRemoteHost,
                "-TlsRemotePort",
                $effectiveContentTlsRemotePort.ToString()
            )
            if (-not [string]::IsNullOrWhiteSpace($effectiveContentTlsConnectHost)) {
                $lobbyProxyArgs += @(
                    "-TlsConnectHost",
                    $effectiveContentTlsConnectHost
                )
            }
            if ($effectiveContentTlsConnectPort -gt 0) {
                $lobbyProxyArgs += @(
                    "-TlsConnectPort",
                    $effectiveContentTlsConnectPort.ToString()
                )
            }
            if ($effectiveContentTlsRemoteRaw) {
                $lobbyProxyArgs += "-TlsRemoteRaw"
            }
        }
    } else {
        # When secure content stays live, local :443 is only used for the post-login
        # secure world hop and must forward both raw and TLS to the local backend.
        $lobbyProxyArgs += "-TlsPassthrough"
        $lobbyProxyArgs += @(
            "-TlsRemoteHost",
            "127.0.0.1",
            "-TlsRemotePort",
            $configuredGameBackendPort.ToString()
        )
    }

    $tlsRemoteHost = if ($script:UseContentTlsRoute) {
        if (-not [string]::IsNullOrWhiteSpace($effectiveContentTlsRemoteHost) -and $effectiveContentTlsRemotePort -gt 0) {
            $effectiveContentTlsRemoteHost
        } else {
            "content.runescape.com"
        }
    } else {
        "127.0.0.1"
    }
    $tlsRemotePort = if ($script:UseContentTlsRoute) {
        if ($effectiveContentTlsRemotePort -gt 0) { $effectiveContentTlsRemotePort } else { 443 }
    } else {
        $configuredGameBackendPort
    }
    $script:EffectiveLobbyTlsPassthrough = $script:UseContentTlsRoute -and $script:UseLobbyTlsPassthroughProxy
    if (-not $script:UseContentTlsRoute) {
        $script:EffectiveLobbyTlsPassthrough = $true
    }
    Write-LaunchTrace (
        "starting lobby proxy with rawRemote={0}:{1} tlsPassthrough={2} tlsRemote={3}:{4} tlsRemoteRaw={5} extraMitmHosts={6}" -f
        $rawRemoteHost,
        $rawRemotePort,
        $script:EffectiveLobbyTlsPassthrough,
        $tlsRemoteHost,
        $tlsRemotePort,
        $effectiveContentTlsRemoteRaw,
        ($extraTlsMitmHosts -join ",")
    )

    Remove-Item $lobbyProxyOut, $lobbyProxyErr -ErrorAction SilentlyContinue

    $launcherArgs = @(
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ('"{0}"' -f $lobbyProxyScript)
    ) + $lobbyProxyArgs

    $launcherProcess = Start-Process `
        -FilePath $powershellExe `
        -ArgumentList $launcherArgs `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -PassThru

    Write-LaunchTrace ("started lobby proxy launcher pid={0} script={1}" -f $launcherProcess.Id, $lobbyProxyScript)
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

function Sync-ContentHostsOverride {
    $use947RetailConfigHost = (
        $script:UseContentTlsRoute -and
        -not $script:UseLobbyTlsPassthroughProxy -and
        $configuredClientBuild -ge 947 -and
        [string]::Equals($script:Effective947StartupConfigHost, "rs.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase)
    )
    if ($script:UseContentTlsRoute -and -not $script:UseLobbyTlsPassthroughProxy -and -not $use947RetailConfigHost) {
        Write-LaunchTrace "content host override skipped=jav-config-rewrite-route"
        return
    }

    if (-not $script:CanWriteHostsFile) {
        Write-LaunchTrace "content host override skipped=no-write-access"
        return
    }

    $hostsScript = if ($use947RetailConfigHost) {
        # The secure 947 retail startup contract must keep rs.config retail-shaped.
        # Clearing any stale hosts overrides here prevents a silent localhost detour.
        $clearContentHostsOverrideScript
    } elseif ($script:UseContentTlsRoute) {
        $setContentHostsOverrideScript
    } else {
        $clearContentHostsOverrideScript
    }
    $action = if ($use947RetailConfigHost) {
        "clear-secure-947-retail-route"
    } elseif ($script:UseContentTlsRoute) {
        "apply"
    } else {
        "clear"
    }

    Write-LaunchTrace ("content host override {0}=start" -f $action)
    & $powershellExe -ExecutionPolicy Bypass -File $hostsScript | Out-Null
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
        $exitCode = 0
    }

    Write-LaunchTrace ("content host override {0}=exitCode:{1}" -f $action, $exitCode)
    if ($exitCode -ne 0) {
        Write-Warning "Content host override script exited with code $exitCode. See data\\debug\\content-hosts-override-error.log for details."
    }
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

function Set-QueryParameter {
    param(
        [string]$Url,
        [string]$Name,
        [string]$Value
    )

    $encodedValue = [uri]::EscapeDataString($Value)
    $pattern = "(?<prefix>[?&])$([Regex]::Escape($Name))=[^&]*"
    if ($Url -match $pattern) {
        return [Regex]::Replace($Url, $pattern, ('$1{0}={1}' -f $Name, $encodedValue), 1)
    }

    if ($Url.Contains("?")) {
        return "${Url}&${Name}=$encodedValue"
    }

    return "${Url}?${Name}=$encodedValue"
}

function Get-QueryParameterValue {
    param(
        [string]$Url,
        [string]$Name
    )

    if ([string]::IsNullOrWhiteSpace($Url) -or [string]::IsNullOrWhiteSpace($Name)) {
        return $null
    }

    $pattern = "(?:[?&])$([Regex]::Escape($Name))=([^&]*)"
    $match = [Regex]::Match($Url, $pattern)
    if (-not $match.Success) {
        return $null
    }

    return [uri]::UnescapeDataString($match.Groups[1].Value)
}

function Remove-QueryParameter {
    param(
        [string]$Url,
        [string]$Name
    )

    if ([string]::IsNullOrWhiteSpace($Url) -or [string]::IsNullOrWhiteSpace($Name)) {
        return $Url
    }

    $updated = [Regex]::Replace($Url, "([?&])$([Regex]::Escape($Name))=[^&]*", '$1')
    $updated = $updated -replace '\?&', '?'
    $updated = $updated -replace '[?&]$', ''
    return $updated
}

function Convert-ToLoopbackJavConfigUrl {
    param(
        [string]$Url,
        [int]$HttpPort
    )

    if ([string]::IsNullOrWhiteSpace($Url) -or $HttpPort -le 0) {
        return $null
    }

    try {
        $uri = [System.Uri]$Url
        $query = $uri.Query
        if (-not [string]::IsNullOrWhiteSpace($query) -and $query.StartsWith("?")) {
            $query = $query.Substring(1)
        }
        $baseUrl = "http://127.0.0.1:$HttpPort/jav_config.ws"
        if ([string]::IsNullOrWhiteSpace($query)) {
            return $baseUrl
        }
        return "${baseUrl}?${query}"
    } catch {
        return $null
    }
}

function Get-UriHostName {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    try {
        $uri = [System.Uri]$Value
        if ([string]::IsNullOrWhiteSpace($uri.Host)) {
            return $null
        }
        return $uri.Host.Trim().ToLowerInvariant()
    } catch {
        return $null
    }
}

function Get-947StartupConfigContent {
    param(
        [string]$ConfigUrl,
        [int]$HttpPort
    )

    if ([string]::IsNullOrWhiteSpace($ConfigUrl) -or $HttpPort -le 0) {
        return $null
    }

    $previewUrl = $ConfigUrl
    $previewUrl = Set-QueryParameter -Url $previewUrl -Name "liveCache" -Value "1"
    $previewUrl = Set-QueryParameter -Url $previewUrl -Name "baseConfigSource" -Value "live"
    $fetchCandidates = @($previewUrl)
    $loopbackUrl = Convert-ToLoopbackJavConfigUrl -Url $previewUrl -HttpPort $HttpPort
    if (-not [string]::IsNullOrWhiteSpace($loopbackUrl) -and $loopbackUrl -ne $previewUrl) {
        $fetchCandidates += $loopbackUrl
    }

    foreach ($candidateUrl in ($fetchCandidates | Select-Object -Unique)) {
        try {
            $response = Invoke-WebRequest -Uri $candidateUrl -UseBasicParsing -TimeoutSec 10
            return $response.Content
        } catch {
            Write-LaunchTrace ("failed to fetch 947 startup config from {0}: {1}" -f $candidateUrl, $_.Exception.Message)
        }
    }

    return $null
}

function Get-947StartupParamMapFromConfigContent {
    param([string]$ConfigContent)

    $result = @{}
    if ([string]::IsNullOrWhiteSpace($ConfigContent)) {
        return $result
    }

    foreach ($rawLine in ($ConfigContent -split "`r?`n")) {
        $line = $rawLine.Trim()
        if (-not $line.StartsWith("param=")) {
            continue
        }

        $payload = $line.Substring(6)
        $separator = $payload.IndexOf("=")
        if ($separator -le 0) {
            continue
        }

        $key = $payload.Substring(0, $separator)
        $value = $payload.Substring($separator + 1)
        if ([string]::IsNullOrWhiteSpace($key)) {
            continue
        }
        $result[$key] = $value
    }

    return $result
}

function Convert-947StartupConfigToParamPairArgs {
    param(
        [string]$ConfigContent,
        [string]$LauncherToken = "A234"
    )

    $paramMap = Get-947StartupParamMapFromConfigContent -ConfigContent $ConfigContent
    if ($paramMap.Count -le 0) {
        return @()
    }

    $orderedKeys = @(
        $paramMap.Keys |
            Sort-Object { [int]$_ }
    )
    $arguments = New-Object System.Collections.Generic.List[string]
    foreach ($key in $orderedKeys) {
        [void]$arguments.Add([string]$key)
        [void]$arguments.Add([string]$paramMap[$key])
    }
    [void]$arguments.Add("launcher")
    [void]$arguments.Add($LauncherToken)
    return @($arguments)
}

function Save-947StartupConfigSnapshot {
    param(
        [string]$ConfigContent,
        [string]$OutputPath
    )

    if ([string]::IsNullOrWhiteSpace($ConfigContent) -or [string]::IsNullOrWhiteSpace($OutputPath)) {
        return $false
    }

    $parent = Split-Path -Parent $OutputPath
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    [System.IO.File]::WriteAllText($OutputPath, $ConfigContent, [System.Text.Encoding]::UTF8)
    return $true
}

function Get-947StartupWorldMitmHostsFromConfigContent {
    param([string]$ConfigContent)

    if ([string]::IsNullOrWhiteSpace($ConfigContent)) {
        return @()
    }

    $hosts = @()
    foreach ($rawLine in ($ConfigContent -split "`r?`n")) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $candidateValue = $null
        if ($line.StartsWith("codebase=")) {
            $candidateValue = $line.Substring("codebase=".Length)
        } elseif ($line.StartsWith("param=3=")) {
            $candidateValue = $line.Substring("param=3=".Length)
        } elseif ($line.StartsWith("param=35=")) {
            $candidateValue = $line.Substring("param=35=".Length)
        } elseif ($line.StartsWith("param=40=")) {
            $candidateValue = $line.Substring("param=40=".Length)
        }

        if ([string]::IsNullOrWhiteSpace($candidateValue)) {
            continue
        }

        $uriHost = Get-UriHostName -Value $candidateValue
        if ([string]::IsNullOrWhiteSpace($uriHost)) {
            continue
        }
        if ($uriHost -in @("localhost", "127.0.0.1", "::1", "content.runescape.com", "rs.config.runescape.com")) {
            continue
        }
        $hosts += $uriHost
    }

    return @($hosts | Select-Object -Unique)
}

function Get-947StartupRouteHostsFromConfigContent {
    param([string]$ConfigContent)

    if ([string]::IsNullOrWhiteSpace($ConfigContent)) {
        return @()
    }

    $hosts = @()
    foreach ($rawLine in ($ConfigContent -split "`r?`n")) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $candidateValue = $null
        if ($line.StartsWith("codebase=")) {
            $candidateValue = $line.Substring("codebase=".Length)
        } elseif ($line.StartsWith("param=3=")) {
            $candidateValue = $line.Substring("param=3=".Length)
        } elseif ($line.StartsWith("param=35=")) {
            $candidateValue = $line.Substring("param=35=".Length)
        } elseif ($line.StartsWith("param=37=")) {
            $candidateValue = $line.Substring("param=37=".Length)
        } elseif ($line.StartsWith("param=40=")) {
            $candidateValue = $line.Substring("param=40=".Length)
        } elseif ($line.StartsWith("param=49=")) {
            $candidateValue = $line.Substring("param=49=".Length)
        }

        if ([string]::IsNullOrWhiteSpace($candidateValue)) {
            continue
        }

        $resolvedHost = Get-UriHostName -Value $candidateValue
        if ([string]::IsNullOrWhiteSpace($resolvedHost)) {
            $resolvedHost = $candidateValue.Trim().ToLowerInvariant()
        }
        if ([string]::IsNullOrWhiteSpace($resolvedHost) -or $resolvedHost -in @("localhost", "127.0.0.1", "::1")) {
            continue
        }
        $hosts += $resolvedHost
    }

    return @($hosts | Select-Object -Unique)
}

function Test-947SecureStartupRedirectHost {
    param([string]$HostName)

    $candidate = $HostName
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $false
    }

    $normalized = $candidate.Trim().ToLowerInvariant()
    return [bool](
        ($normalized -match '^(?:world|lobby)[0-9]+[a-z]*\.runescape\.com$|^(?:world|lobby)\*\.runescape\.com$') -or
        ($normalized -match '^content[a-z0-9-]*\.runescape\.com$|^content\*\.runescape\.com$')
    )
}

function Get-947SecureRetailWorldFleetHosts {
    # The Frida resolve hook now supports wildcard hostname rules, so keep the
    # secure-retail startup fleet compact while still catching the content
    # bootstrap host, the world host, and the later secure lobby handoff host.
    return @(
        "content*.runescape.com"
        "world*.runescape.com"
        "lobby*.runescape.com"
    )
}

function Get-947StartupWorldMitmHosts {
    param(
        [string]$ConfigUrl,
        [int]$HttpPort
    )

    if ([string]::IsNullOrWhiteSpace($ConfigUrl) -or $HttpPort -le 0) {
        return @()
    }

    $content = Get-947StartupConfigContent -ConfigUrl $ConfigUrl -HttpPort $HttpPort
    if ([string]::IsNullOrWhiteSpace($content)) {
        return @()
    }

    return @(Get-947StartupWorldMitmHostsFromConfigContent -ConfigContent $content)
}

function Set-UrlHost {
    param(
        [string]$Url,
        [string]$HostName
    )

    return [Regex]::Replace($Url, '^(https?://)([^/:?]+)', ('$1{0}' -f $HostName), 1)
}

function Test-HostsFileWriteAccess {
    param([string]$Path)

    try {
        $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::ReadWrite)
        $stream.Dispose()
        return $true
    } catch {
        return $false
    }
}

function Test-RecentD3DDeviceRemoved {
    param([string[]]$LogPaths)

    foreach ($path in $LogPaths) {
        if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path $path)) {
            continue
        }

        try {
            $tail = @(Get-Content -Path $path -Tail 80 -ErrorAction Stop)
        } catch {
            continue
        }

        if (($tail -join [Environment]::NewLine) -match 'device was removed|0x887A0020') {
            return $true
        }
    }

    return $false
}

function Test-TlsPassthroughRouteReady {
    param([string]$HostName)

    try {
        $resolvedAddresses = @(
            Resolve-DnsName $HostName -Type A -ErrorAction Stop |
                Select-Object -ExpandProperty IPAddress
        )
        return $resolvedAddresses -contains "127.0.0.1"
    } catch {
        return $false
    }
}

function Test-ContentTlsMitmRouteReady {
    param(
        [string]$ProxyScript,
        [string]$CertScript
    )

    return (Test-Path $ProxyScript) -and (Test-Path $CertScript)
}

function Get-CanonicalMitmDnsNames {
    param([string]$LobbyHost)

    $primaryHost = Resolve-CanonicalMitmPrimaryDnsName -LobbyHost $LobbyHost
    return (
        @(
            $primaryHost
            $LobbyHost
            $script:ConfiguredTlsExtraMitmHosts
            "content.runescape.com"
            "rs.config.runescape.com"
            "localhost"
            "127.0.0.1"
            "::1"
        ) |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Select-Object -Unique
    ) -join ","
}

function Resolve-CanonicalMitmPrimaryDnsName {
    param([string]$LobbyHost)

    # The launcher rewrites the client-facing content host to localhost, so the
    # primary MITM certificate identity should stay loopback-stable even when
    # the configured upstream lobby hostname remains a real RuneScape host.
    return $defaultMitmPrimaryHost
}

function Get-CanonicalMitmTrustState {
    param(
        [string]$LobbyHost,
        [switch]$Repair
    )

    $primaryHost = Resolve-CanonicalMitmPrimaryDnsName -LobbyHost $LobbyHost
    $dnsNames = Get-CanonicalMitmDnsNames -LobbyHost $LobbyHost
    if ($Repair) {
        $payload = & $certScript -DnsName $dnsNames -PrimaryDnsName $primaryHost
    } else {
        $payload = & $certScript -DnsName $dnsNames -PrimaryDnsName $primaryHost -CheckOnly
    }
    return $payload | ConvertFrom-Json
}

function Start-CanonicalMitmTrustRepair {
    param([string]$LobbyHost)

    $primaryHost = Resolve-CanonicalMitmPrimaryDnsName -LobbyHost $LobbyHost
    $dnsNames = @(Get-CanonicalMitmDnsNames -LobbyHost $LobbyHost)
    $repairToken = [guid]::NewGuid().ToString("N")
    $stdoutPath = Join-Path $root ("tmp-canonical-mitm-trust-repair-{0}.out.log" -f $repairToken)
    $stderrPath = Join-Path $root ("tmp-canonical-mitm-trust-repair-{0}.err.log" -f $repairToken)
    $argumentList = @(
        "-NoProfile"
        "-ExecutionPolicy"
        "Bypass"
        "-File"
        $certScript
        "-DnsName"
        ($dnsNames -join ",")
        "-PrimaryDnsName"
        $primaryHost
    ) | ForEach-Object { Quote-CmdArgument -Value $_ }
    $process = Start-Process `
        -FilePath $powershellExe `
        -ArgumentList ($argumentList -join " ") `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    return [pscustomobject]@{
        Process = $process
        PrimaryDnsName = $primaryHost
        DnsNames = $dnsNames
        StdoutPath = $stdoutPath
        StderrPath = $stderrPath
    }
}

function Ensure-CanonicalMitmTrust {
    param([string]$LobbyHost)

    $trustState = Get-CanonicalMitmTrustState -LobbyHost $LobbyHost
    $repaired = $false
    if (-not [bool]$trustState.TrustHealthy) {
        Write-LaunchTrace "canonical mitm trust unhealthy; attempting repair"
        $repair = Start-CanonicalMitmTrustRepair -LobbyHost $LobbyHost
        Write-LaunchTrace ("started canonical mitm trust repair pid={0} primary={1} dns={2}" -f $repair.Process.Id, $repair.PrimaryDnsName, ($repair.DnsNames -join ","))
        $deadline = (Get-Date).AddSeconds(120)
        do {
            Start-Sleep -Milliseconds 500
            $trustState = Get-CanonicalMitmTrustState -LobbyHost $LobbyHost
            if ([bool]$trustState.TrustHealthy) {
                $repaired = $true
                break
            }
            $repairProcess = Get-Process -Id $repair.Process.Id -ErrorAction SilentlyContinue
        } while ($null -ne $repairProcess -and (Get-Date) -lt $deadline)

        $repairProcess = Get-Process -Id $repair.Process.Id -ErrorAction SilentlyContinue
        if ($null -ne $repairProcess) {
            try {
                taskkill /PID $repair.Process.Id /T /F | Out-Null
            } catch {}
            if ([bool]$trustState.TrustHealthy) {
                Write-LaunchTrace ("terminated canonical mitm trust repair pid={0} after trust became healthy" -f $repair.Process.Id)
            } else {
                Write-LaunchTrace ("terminated canonical mitm trust repair pid={0} after timeout stdout={1} stderr={2}" -f $repair.Process.Id, $repair.StdoutPath, $repair.StderrPath)
            }
        }
    }
    if (-not [bool]$trustState.TrustHealthy) {
        throw "Canonical MITM TLS trust is unhealthy. Subject=$($trustState.ActiveSubject) Thumbprint=$($trustState.ActiveThumbprint) PfxPath=$($trustState.PfxPath)"
    }
    if (-not [bool]$trustState.RootTrusted) {
        throw "Canonical MITM TLS trust is missing from Cert:\\CurrentUser\\Root. Subject=$($trustState.ActiveSubject) Thumbprint=$($trustState.ActiveThumbprint)"
    }
    if (-not [bool]$trustState.DirectLeafTrusted) {
        throw "Canonical MITM TLS leaf is not directly trusted in Cert:\\CurrentUser\\TrustedPeople or Cert:\\CurrentUser\\Root. Subject=$($trustState.ActiveSubject) Thumbprint=$($trustState.ActiveThumbprint)"
    }

    Write-LaunchTrace ("canonical mitm trust ok subject={0} thumbprint={1} repaired={2}" -f $trustState.ActiveSubject, $trustState.ActiveThumbprint, $repaired)
    return [pscustomobject]@{
        TrustState = $trustState
        Repaired = $repaired
    }
}

function Get-ConfiguredServerValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$DefaultValue
    )

    if (-not (Test-Path $Path)) {
        return $DefaultValue
    }

    foreach ($line in (Get-Content $Path)) {
        if ($line -match ('^\s*{0}\s*=\s*"([^"]+)"' -f [Regex]::Escape($Key))) {
            return $Matches[1]
        }
    }

    return $DefaultValue
}

function Get-ConfiguredServerIntValue {
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
                    $_.CommandLine -like "*launch-win64c-live.ps1*" -or
                    $_.CommandLine -like "*keep_local_live_stack.ps1*" -or
                    $_.CommandLine -like "*launch_lobby_tls_terminator.ps1*" -or
                    $_.CommandLine -like "*setup_lobby_tls_cert.ps1*" -or
                    $_.CommandLine -like "*launch_game_tls_terminator.ps1*" -or
                    $_.CommandLine -like "*patched.exe*" -or
                    $_.CommandLine -like "*tcp_proxy.py*" -or
                    $_.CommandLine -like "*tls_terminate_proxy.py*" -or
                    $_.CommandLine -like "*OpenNXT.bat*run-server*" -or
                    $_.CommandLine -like "*com.opennxt.MainKt*"
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

function Stop-InstalledJagexLauncherProcesses {
    $launcherPids = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.ProcessId -ne $PID -and
                (
                    $_.Name -eq "JagexLauncher.exe" -or
                    $_.Name -eq "Jagex Launcher.exe" -or
                    ($null -ne $_.ExecutablePath -and $_.ExecutablePath -like "*\\Jagex Launcher\\JagexLauncher.exe")
                )
            } |
            Select-Object -ExpandProperty ProcessId -Unique
    )

    foreach ($processId in $launcherPids) {
        try {
            taskkill /PID $processId /F | Out-Null
            Write-LaunchTrace ("stopped installed Jagex Launcher pid={0}" -f $processId)
        } catch {}
    }
}

function Stop-WrapperLaunchArtifacts {
    param([string]$WrapperExePath)

    if ([string]::IsNullOrWhiteSpace($WrapperExePath) -or -not (Test-Path $WrapperExePath)) {
        return @()
    }

    $resolvedWrapperPath = [System.IO.Path]::GetFullPath($WrapperExePath)
    $helperScriptName = "launch_runescape_wrapper_rewrite.py"
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $staleWrapperPids = @(
        $processes |
            Where-Object {
                $_.ProcessId -ne $PID -and
                $null -ne $_.ExecutablePath -and
                [string]::Equals($_.ExecutablePath, $resolvedWrapperPath, [System.StringComparison]::OrdinalIgnoreCase)
            } |
            Select-Object -ExpandProperty ProcessId -Unique
    )
    $helperPids = @(
        $processes |
            Where-Object {
                $_.ProcessId -ne $PID -and
                -not [string]::IsNullOrWhiteSpace($_.CommandLine) -and
                $_.CommandLine -like "*$helperScriptName*" -and
                $_.CommandLine -like "*$resolvedWrapperPath*"
            } |
            Select-Object -ExpandProperty ProcessId -Unique
    )
    $relatedPids = @()
    if ($staleWrapperPids.Count -gt 0) {
        $relatedPids = @(
            $processes |
                Where-Object {
                    $_.ProcessId -ne $PID -and
                    $staleWrapperPids -contains $_.ParentProcessId -and
                    (
                        $_.Name -eq "RuneScape.exe" -or
                        $_.Name -eq "rs2client.exe" -or
                        ($null -ne $_.ExecutablePath -and ($_.ExecutablePath -like "*\RuneScape.exe" -or $_.ExecutablePath -like "*\rs2client.exe"))
                    )
                } |
                Select-Object -ExpandProperty ProcessId -Unique
        )
    }

    $targetPids = @(
        @($helperPids + $staleWrapperPids + $relatedPids) |
            Sort-Object -Unique
    )

    foreach ($processId in $targetPids) {
        try {
            taskkill /PID $processId /T /F | Out-Null
            Write-LaunchTrace ("stopped stale wrapper artifact pid={0}" -f $processId)
        } catch {}
    }

    return $targetPids
}

Stop-ExistingNetTestProcesses
Stop-InstalledJagexLauncherProcesses
Remove-Item $launchTrace -ErrorAction SilentlyContinue
Remove-Item $launchStateFile -ErrorAction SilentlyContinue
Remove-Item $startupConfigSnapshotPath -ErrorAction SilentlyContinue
Write-LaunchTrace "starting launch-win64c-live"
$script:CanWriteHostsFile = Test-HostsFileWriteAccess -Path $hostsFile
$script:TlsPassthroughRouteReady = Test-TlsPassthroughRouteReady -HostName $tlsPassthroughConfigHost
$script:ContentTlsMitmRouteReady = Test-ContentTlsMitmRouteReady -ProxyScript $lobbyProxyScript -CertScript $certScript
$autoSelectContentTlsMitm = (-not $DisableLobbyTlsPassthroughAuto.IsPresent) -and $script:ContentTlsMitmRouteReady
$autoSelectTlsPassthrough = (
    -not $DisableLobbyTlsPassthroughAuto.IsPresent -and
    -not $autoSelectContentTlsMitm -and
    $script:TlsPassthroughRouteReady
)
$script:UseContentTlsRoute = (
    $LobbyTlsPassthrough.IsPresent -or
    $ForceLobbyTlsMitm.IsPresent -or
    $autoSelectContentTlsMitm -or
    $autoSelectTlsPassthrough
)
$script:UseLobbyTlsPassthroughProxy = (
    $LobbyTlsPassthrough.IsPresent -or
    (
        -not $ForceLobbyTlsMitm.IsPresent -and
        -not $autoSelectContentTlsMitm -and
        $autoSelectTlsPassthrough
    )
)
$script:ContentRouteMode = if ($script:UseContentTlsRoute -and -not $script:UseLobbyTlsPassthroughProxy) {
    "content-only-local-mitm"
} elseif ($script:UseLobbyTlsPassthroughProxy) {
    "tls-passthrough"
} else {
    "disabled"
}
$script:LobbyTlsRoutingMode = if ($script:UseContentTlsRoute -and -not $script:UseLobbyTlsPassthroughProxy) {
    "auto-classify"
} elseif ($script:UseLobbyTlsPassthroughProxy -or -not $script:UseContentTlsRoute) {
    "passthrough"
} else {
    "disabled"
}
$configuredLobbyHost = Get-ConfiguredServerValue -Path $serverConfigPath -Key "hostname" -DefaultValue "lobby45a.runescape.com"
$configuredGameHost = Get-ConfiguredServerValue -Path $serverConfigPath -Key "gameHostname" -DefaultValue "127.0.0.1"
if ([string]::IsNullOrWhiteSpace($configuredGameHost)) {
    $configuredGameHost = $configuredLobbyHost
}
$canonicalLoopbackLobbyHost = if ($configuredLobbyHost -in @("127.0.0.1", "::1", "localhost")) { "localhost" } else { $configuredLobbyHost }
$script:ConfiguredMitmLobbyHost = $configuredLobbyHost
$script:CanonicalMitmPrimaryDnsName = Resolve-CanonicalMitmPrimaryDnsName -LobbyHost $configuredLobbyHost
$canonicalLoopbackGameHost = if ($configuredGameHost -in @("127.0.0.1", "::1", "localhost")) { "localhost" } else { $configuredGameHost }
$configuredHttpPort = Get-ConfiguredServerIntValue -Path $serverConfigPath -Key "http" -DefaultValue 8081
$configuredGamePort = Get-ConfiguredServerIntValue -Path $serverConfigPath -Key "game" -DefaultValue 43594
$configuredGameBackendPort = Get-ConfiguredServerIntValue -Path $serverConfigPath -Key "gameBackend" -DefaultValue 43596
$script:EffectiveBypassGameProxy = if ($script:UseContentTlsRoute) {
    $BypassGameProxy.IsPresent
} else {
    $BypassGameProxy.IsPresent -or ($configuredGameBackendPort -eq $configuredGamePort)
}
if ($configuredClientBuild -ge 947) {
    # Keep patched 947 live runs on the secure retail splash transport by
    # default. We can still opt into a local jav_config/bootstrap route
    # explicitly when a later-stage experiment calls for it.
    $launchArg = "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0"
} else {
    $launchArg = "http://${canonicalLoopbackLobbyHost}:$configuredHttpPort/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&gameHostOverride=$canonicalLoopbackGameHost&gamePortOverride=$configuredGamePort"
}
Write-LaunchTrace ("hostsFile writeAccess={0}" -f $script:CanWriteHostsFile)
Write-LaunchTrace ("tlsPassthroughRouteReady={0}" -f $script:TlsPassthroughRouteReady)
Write-LaunchTrace ("contentTlsMitmRouteReady={0}" -f $script:ContentTlsMitmRouteReady)
Write-LaunchTrace ("forceLobbyTlsMitm={0}" -f $ForceLobbyTlsMitm.IsPresent)
Write-LaunchTrace ("disableLobbyTlsPassthroughAuto={0}" -f $DisableLobbyTlsPassthroughAuto.IsPresent)
Write-LaunchTrace ("useContentTlsRoute={0}" -f $script:UseContentTlsRoute)
Write-LaunchTrace ("useLobbyTlsPassthroughProxy={0}" -f $script:UseLobbyTlsPassthroughProxy)
Write-LaunchTrace ("contentRouteMode={0}" -f $script:ContentRouteMode)
Write-LaunchTrace ("lobbyTlsRoutingMode={0}" -f $script:LobbyTlsRoutingMode)
Write-LaunchTrace ("contentTlsRemoteHost={0}" -f $ContentTlsRemoteHost)
Write-LaunchTrace ("contentTlsRemotePort={0}" -f $ContentTlsRemotePort)
Write-LaunchTrace ("contentTlsRemoteRaw={0}" -f $ContentTlsRemoteRaw.IsPresent)
Write-LaunchTrace ("configuredLobbyHost={0}" -f $configuredLobbyHost)
Write-LaunchTrace ("canonicalLoopbackLobbyHost={0}" -f $canonicalLoopbackLobbyHost)
Write-LaunchTrace ("canonicalMitmLobbyHost={0}" -f $script:ConfiguredMitmLobbyHost)
Write-LaunchTrace ("canonicalMitmPrimaryDnsName={0}" -f $script:CanonicalMitmPrimaryDnsName)
Write-LaunchTrace ("configuredGameHost={0}" -f $configuredGameHost)
Write-LaunchTrace ("canonicalLoopbackGameHost={0}" -f $canonicalLoopbackGameHost)
Write-LaunchTrace ("configuredHttpPort={0}" -f $configuredHttpPort)
Write-LaunchTrace ("configuredGamePort={0}" -f $configuredGamePort)
Write-LaunchTrace ("configuredGameBackendPort={0}" -f $configuredGameBackendPort)
Write-LaunchTrace ("effectiveBypassGameProxy={0}" -f $script:EffectiveBypassGameProxy)
if (-not $script:UseContentTlsRoute -and -not $BypassGameProxy.IsPresent -and $script:EffectiveBypassGameProxy) {
    Write-LaunchTrace "auto-bypassing game proxy because configured gameBackend equals public game port"
}

if ($script:UseContentTlsRoute -and $BypassGameProxy.IsPresent) {
    Write-LaunchTrace "canonical route blocked=bypass-game-proxy"
    throw "BypassGameProxy is not supported on the canonical no-hosts content MITM route."
}

if ($script:UseContentTlsRoute -and $configuredGameBackendPort -eq $configuredGamePort) {
    Write-LaunchTrace "canonical route blocked=game-port-split-collapsed"
    throw "Canonical no-hosts content MITM route requires game != gameBackend. Found $configuredGamePort/$configuredGameBackendPort."
}

if ($ForceLobbyTlsMitm.IsPresent -and -not $script:ContentTlsMitmRouteReady) {
    Write-LaunchTrace "mitm route blocked=missing-prerequisites"
    throw "ForceLobbyTlsMitm requested but the local TLS MITM route is not ready."
}

if ($UsePatchedLauncher -and $UseOriginalClient) {
    throw "UseOriginalClient cannot be combined with UsePatchedLauncher"
}

Get-ListeningProcessIds -Ports @(443, $configuredHttpPort, $configuredGamePort, $configuredGameBackendPort) |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {}
    }

Get-Process -Name rs2client,RuneScape -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        taskkill /PID $_.Id /F | Out-Null
    } catch {}
}

Get-CimInstance Win32_Process |
    Where-Object { $null -ne $_.ExecutablePath -and $_.ExecutablePath -eq $launcherExe } |
    ForEach-Object {
        try {
            taskkill /PID $_.ProcessId /F | Out-Null
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
$runtimeCacheSyncResult = $null
$script:ConfiguredTlsExtraMitmHosts = @()
Ensure-InstalledServerCurrent
$openNxtBat = Join-Path $root "build\\install\\OpenNXT\\bin\\OpenNXT.bat"
$gradleBat = Join-Path $root "gradlew.bat"
$serverArgs = @("run-server")
$configUrlOverrideExplicit = $PSBoundParameters.ContainsKey("ConfigUrlOverride") -and -not [string]::IsNullOrWhiteSpace($ConfigUrlOverride)
$effectiveLaunchArg = if ([string]::IsNullOrWhiteSpace($ConfigUrlOverride)) { $launchArg } else { $ConfigUrlOverride }
$effectiveUseOriginalClient = $UseOriginalClient.IsPresent
$prefer947PatchedDirectClient = (
    $configuredClientBuild -ge 947 -and
    -not $UsePatchedLauncher -and
    -not $UseRuneScapeWrapper.IsPresent
)
$downloadMetadataSourceExplicit = $PSBoundParameters.ContainsKey("DownloadMetadataSource")
$existingDownloadMetadataSource = Get-QueryParameterValue -Url $effectiveLaunchArg -Name "downloadMetadataSource"
$resolvedDownloadMetadataSource = if ($downloadMetadataSourceExplicit) {
    $DownloadMetadataSource.Trim().ToLowerInvariant()
} elseif (-not [string]::IsNullOrWhiteSpace($existingDownloadMetadataSource)) {
    $existingDownloadMetadataSource.Trim().ToLowerInvariant()
} elseif (
    $configuredClientBuild -ge 947 -and
    $prefer947PatchedDirectClient -and
    [string]::Equals((Get-UriHostName -Value $effectiveLaunchArg), "rs.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase)
) {
    # Match the safer client-only retail-shaped startup baseline: preserve the
    # live base-config + original metadata pair unless the caller explicitly
    # overrides downloadMetadataSource.
    "original"
} else {
    if ($effectiveUseOriginalClient) { "original" } else { "patched" }
}
$effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "downloadMetadataSource" -Value $resolvedDownloadMetadataSource
if ($configuredClientBuild -ge 947) {
    # Default the 947 launch route according to the selected client family, but
    # preserve an explicit ConfigUrlOverride so local live-snapshot
    # experiments are not silently rewritten.
    if (-not $configUrlOverrideExplicit) {
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "hostRewrite" -Value "0"
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "lobbyHostRewrite" -Value "0"
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "gameHostRewrite" -Value "0"
        if ([string]::Equals((Get-UriHostName -Value $effectiveLaunchArg), "rs.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase) -and $prefer947PatchedDirectClient) {
            # Keep the visible 947 direct startup contract retail-shaped and
            # let the redirect/runtime-repair layer steer the secure splash
            # bootstrap. Forcing world/content/codebase rewrites here traps the
            # client in the local raw 255/* refresh loop before login. Preserve
            # the live base-config + original metadata pair so the later
            # world-local follow-up stays on the original+live-session
            # contract instead of dropping into the localhost bootstrap loop.
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "gamePortOverride"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "0"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSnapshotPath"
        } elseif ([string]::Equals((Get-UriHostName -Value $effectiveLaunchArg), "rs.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase)) {
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "gamePortOverride"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "0"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "liveCache"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSnapshotPath"
        } else {
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "1"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "1"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "1"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource" -Value "live"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "liveCache" -Value "1"
        }
    }
    $use947RetailConfigHost = [string]::Equals((Get-UriHostName -Value $effectiveLaunchArg), "rs.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase)
    if ($use947RetailConfigHost) {
        if ($prefer947PatchedDirectClient) {
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "gamePortOverride"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "0"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSnapshotPath"
        } elseif (-not $configUrlOverrideExplicit) {
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "0"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "liveCache"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSnapshotPath"
        }
    } else {
        if ([string]::IsNullOrWhiteSpace((Get-QueryParameterValue -Url $effectiveLaunchArg -Name "codebaseRewrite"))) {
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "1"
        }
        if ([string]::IsNullOrWhiteSpace((Get-QueryParameterValue -Url $effectiveLaunchArg -Name "baseConfigSource"))) {
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource" -Value "live"
        }
        if ([string]::IsNullOrWhiteSpace((Get-QueryParameterValue -Url $effectiveLaunchArg -Name "liveCache"))) {
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "liveCache" -Value "1"
        }
    }
}
if ($script:UseContentTlsRoute) {
    if (-not $prefer947PatchedDirectClient -and -not $configUrlOverrideExplicit) {
        # Keep the default 947 wrapper route fully retail-shaped. Explicit
        # ConfigUrlOverride experiments are allowed to keep their local rewrite
        # contract, but the default live path must not reintroduce a localhost
        # codebase hop during the splash bootstrap.
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "hostRewrite" -Value "0"
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "lobbyHostRewrite" -Value "0"
        if ($configuredClientBuild -ge 947) {
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "gamePortOverride"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "gameHostRewrite" -Value "0"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "liveCache"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSnapshotPath"
        } else {
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "1"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "gameHostOverride" -Value $canonicalLoopbackGameHost
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "gamePortOverride" -Value $configuredGamePort
        }
    }
} else {
    if (-not $configUrlOverrideExplicit) {
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "0"
    }
}
if ($useRuneScapeWrapperPreview) {
    if ($configuredClientBuild -lt 947) {
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "1"
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource" -Value "compressed"
    }
}
if (
    $configuredClientBuild -ge 947 -and
    $prefer947PatchedDirectClient -and
    [string]::Equals((Get-UriHostName -Value $effectiveLaunchArg), "rs.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase)
) {
    # Final safety net: the direct 947 retail-shaped startup path should keep
    # the live base-config contract even if an earlier normalization branch
    # removed it while rewriting the rest of the URL back to retail-shaped
    # defaults.
    if ([string]::IsNullOrWhiteSpace((Get-QueryParameterValue -Url $effectiveLaunchArg -Name "baseConfigSource"))) {
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource" -Value "live"
    }
    if ([string]::IsNullOrWhiteSpace((Get-QueryParameterValue -Url $effectiveLaunchArg -Name "liveCache"))) {
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "liveCache" -Value "1"
    }
}
$script:Effective947StartupConfigHost = if ($configuredClientBuild -ge 947) { Get-UriHostName -Value $effectiveLaunchArg } else { $null }
$clientArgs = @($effectiveLaunchArg)
$useRuneScapeWrapperPreview = -not $prefer947PatchedDirectClient
$useDirectPatchedPreview = $prefer947PatchedDirectClient
$resolveRedirectSpecs = @()
$autoManageGraphicsCompat = $AutoSwitchGraphicsCompat.IsPresent -or
    (($useRuneScapeWrapperPreview -or $useDirectPatchedPreview) -and $configuredClientBuild -ge 947)
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

function Get-RuntimeArchiveCandidateNames {
    param(
        [int]$ArchiveId,
        [switch]$IncludeCorePrefixedAliases
    )

    if ($IncludeCorePrefixedAliases) {
        return @(
            ("js5-{0}.jcache" -f $ArchiveId)
            ("core-js5-{0}.jcache" -f $ArchiveId)
        )
    }

    return @(("js5-{0}.jcache" -f $ArchiveId))
}

function Get-RuntimeArchiveState {
    param(
        [string]$RuntimeCacheDir,
        [int]$ArchiveId,
        [switch]$IncludeCorePrefixedAliases,
        [int]$StubMaxLength = 12288
    )

    $candidateRecords = @(
        foreach ($candidateName in (Get-RuntimeArchiveCandidateNames -ArchiveId $ArchiveId -IncludeCorePrefixedAliases:$IncludeCorePrefixedAliases)) {
            $candidatePath = Join-Path $RuntimeCacheDir $candidateName
            $candidateItem = if (Test-Path $candidatePath) {
                Get-Item -LiteralPath $candidatePath -ErrorAction SilentlyContinue
            } else {
                $null
            }

            [pscustomobject]@{
                Name = $candidateName
                Path = $candidatePath
                Exists = $null -ne $candidateItem
                Length = if ($candidateItem) { [int64]$candidateItem.Length } else { $null }
            }
        }
    )

    $selectedRecord = $candidateRecords | Where-Object { $_.Exists } | Select-Object -First 1
    return [pscustomobject]@{
        ArchiveId = $ArchiveId
        Exists = $null -ne $selectedRecord
        PreferredPath = if ($selectedRecord) { $selectedRecord.Path } else { $candidateRecords[0].Path }
        PreferredName = if ($selectedRecord) { $selectedRecord.Name } else { $candidateRecords[0].Name }
        Length = if ($selectedRecord) { $selectedRecord.Length } else { $null }
        IsStub = $null -ne $selectedRecord -and $selectedRecord.Length -le $StubMaxLength
        CandidatePaths = @($candidateRecords | ForEach-Object { $_.Path })
        ExistingPaths = @($candidateRecords | Where-Object { $_.Exists } | ForEach-Object { $_.Path })
    }
}

function Get-SharedReadFileSha256 {
    param([string]$Path)

    $stream = $null
    $hasher = $null
    try {
        $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        $hashBytes = $hasher.ComputeHash($stream)
        return ([System.BitConverter]::ToString($hashBytes)).Replace("-", "")
    } finally {
        if ($hasher) {
            $hasher.Dispose()
        }
        if ($stream) {
            $stream.Dispose()
        }
    }
}

function Get-RuntimeArchiveSqliteShape {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $null
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        return $null
    }

    $pythonScript = @'
import json
import sqlite3
import sys

path = sys.argv[1]
result = {"cache_rows": 0, "cache_index_rows": 0}
try:
    uri = "file:" + path + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    cursor = connection.cursor()
    cache_rows = cursor.execute("select count(*) from cache").fetchone()
    cache_index_rows = cursor.execute("select count(*) from cache_index").fetchone()
    result["cache_rows"] = 0 if not cache_rows else int(cache_rows[0] or 0)
    result["cache_index_rows"] = 0 if not cache_index_rows else int(cache_index_rows[0] or 0)
    connection.close()
except Exception:
    pass

print(json.dumps(result))
'@

    try {
        $raw = $pythonScript | & $pythonCommand.Source - $Path 2>$null
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return $null
        }
        return $raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Test-RuntimeArchiveHasMissingReferenceTable {
    param(
        [string]$SourcePath,
        [string]$RuntimePath
    )

    if (-not (Test-Path $SourcePath) -or -not (Test-Path $RuntimePath)) {
        return $false
    }

    $sourceShape = Get-RuntimeArchiveSqliteShape -Path $SourcePath
    if ($null -eq $sourceShape -or [int]$sourceShape.cache_index_rows -le 0) {
        return $false
    }

    $runtimeShape = Get-RuntimeArchiveSqliteShape -Path $RuntimePath
    if ($null -eq $runtimeShape) {
        return $false
    }

    return [int]$runtimeShape.cache_index_rows -le 0
}

function Test-RuntimeArchiveMatchesSource {
    param(
        [string]$SourceCacheDir,
        [string]$RuntimeCacheDir,
        [int]$ArchiveId
    )

    $sourcePath = Join-Path $SourceCacheDir ("js5-{0}.jcache" -f $ArchiveId)
    $runtimePath = Join-Path $RuntimeCacheDir ("js5-{0}.jcache" -f $ArchiveId)
    if (-not (Test-Path $sourcePath) -or -not (Test-Path $runtimePath)) {
        return $false
    }

    $sourceItem = Get-Item -LiteralPath $sourcePath -ErrorAction SilentlyContinue
    $runtimeItem = Get-Item -LiteralPath $runtimePath -ErrorAction SilentlyContinue
    if ($null -eq $sourceItem -or $null -eq $runtimeItem) {
        return $false
    }
    if (Test-RuntimeArchiveHasMissingReferenceTable -SourcePath $sourcePath -RuntimePath $runtimePath) {
        return $false
    }
    if ([int64]$sourceItem.Length -ne [int64]$runtimeItem.Length) {
        return $false
    }

    $sourceHash = Get-SharedReadFileSha256 -Path $sourcePath
    $runtimeHash = Get-SharedReadFileSha256 -Path $runtimePath
    return $sourceHash -eq $runtimeHash
}

$runtimeCopiedHotArchiveIds = @()
$runtimeAutoRepairReason = $null
$runtimeShouldAutoRepairHotCache947 = $false
$runtimeHotCacheRepairArchiveIds = @()
$runtimeHotStubArchiveIds = @()
$runtimeHotMissingReferenceTableArchiveIds = @()
$runtimeHotArchiveParityMismatchIds = @()
$runtimeShouldPreserveHotArchiveSet = $false
$runtimeForceRetailRefreshHotArchiveSet = $false
$runtimeHotCacheRepairResult = $null

$runtimeUsesRetailStartupConfig = $configuredClientBuild -ge 947 -and $use947RetailConfigHost
$runtimeAutoSkipCacheSync947Retail = $configuredClientBuild -ge 947 -and $runtimeUsesRetailStartupConfig -and $prefer947PatchedDirectClient
$runtimeCacheSyncSkippedEffective = [bool]($SkipRuntimeCacheSync.IsPresent -or $runtimeAutoSkipCacheSync947Retail)
if ($runtimeAutoSkipCacheSync947Retail) {
    Write-LaunchTrace "runtime cache sync auto-skipped for 947 retail-shaped direct-patched path"
}

if (-not $runtimeCacheSyncSkippedEffective -and $configuredClientBuild -ge 947 -and -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and (Test-Path $runtimeCacheSyncScript)) {
    $runtimeCacheSourceDir = Join-Path $root "data\\cache"
    $runtimeCacheTargetDir = Join-Path $env:ProgramData "Jagex\\RuneScape"
    $runtimeAliasSeedingEnabled = $configuredClientBuild -ge 947
    Write-LaunchTrace ("runtime cache sync start source={0} runtime={1}" -f $runtimeCacheSourceDir, $runtimeCacheTargetDir)
    $runtimeSourceFiles = @(
        Get-ChildItem -Path $runtimeCacheSourceDir -Filter "js5-*.jcache" -File -ErrorAction SilentlyContinue
    )
    $runtimeSourceArchiveIds = @(
        $runtimeSourceFiles |
            ForEach-Object {
                if ($_.Name -match '^js5-(\d+)\.jcache$') {
                    [int]$Matches[1]
                }
            } |
            Sort-Object -Unique
    )
    $runtimeTargetFiles = @(
        Get-ChildItem -Path $runtimeCacheTargetDir -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^(?:core-)?js5-\d+\.jcache$' }
    )
    $runtimeTargetArchiveCount = @(
        foreach ($archiveId in $runtimeSourceArchiveIds) {
            $runtimeArchiveState = Get-RuntimeArchiveState -RuntimeCacheDir $runtimeCacheTargetDir -ArchiveId $archiveId -IncludeCorePrefixedAliases:$runtimeAliasSeedingEnabled
            if ($runtimeArchiveState.Exists) {
                $archiveId
            }
        }
    )
    $runtimeHotStubArchiveIds = @(
        foreach ($archiveId in $runtimeHotArchiveIds947) {
            $runtimeArchiveState = Get-RuntimeArchiveState -RuntimeCacheDir $runtimeCacheTargetDir -ArchiveId $archiveId -IncludeCorePrefixedAliases:$runtimeAliasSeedingEnabled
            if ($runtimeArchiveState.IsStub) {
                $archiveId
            }
        }
    )
    $runtimeMissingHotArchiveIds = @(
        foreach ($archiveId in $runtimeHotArchiveIds947) {
            $runtimeArchiveState = Get-RuntimeArchiveState -RuntimeCacheDir $runtimeCacheTargetDir -ArchiveId $archiveId -IncludeCorePrefixedAliases:$runtimeAliasSeedingEnabled
            if (-not $runtimeArchiveState.Exists) {
                $archiveId
            }
        }
    )
    $runtimeHotMissingReferenceTableArchiveIds = @(
        foreach ($archiveId in $runtimeHotArchiveIds947) {
            $runtimeArchiveState = Get-RuntimeArchiveState -RuntimeCacheDir $runtimeCacheTargetDir -ArchiveId $archiveId -IncludeCorePrefixedAliases:$runtimeAliasSeedingEnabled
            $sourceArchivePath = Join-Path $runtimeCacheSourceDir ("js5-{0}.jcache" -f $archiveId)
            if (
                $runtimeArchiveState.Exists -and
                (Test-RuntimeArchiveHasMissingReferenceTable -SourcePath $sourceArchivePath -RuntimePath $runtimeArchiveState.PreferredPath)
            ) {
                $archiveId
            }
        }
    )
    $runtimePromoteToFullSync = $runtimeUsesRetailStartupConfig -or ($prefer947PatchedDirectClient -and ($runtimeTargetArchiveCount.Count -lt $runtimeSourceFiles.Count -or $runtimeHotStubArchiveIds.Count -gt 0 -or $runtimeHotMissingReferenceTableArchiveIds.Count -gt 0))
    $runtimeSyncMode = if ($runtimePromoteToFullSync) { "full" } else { "seed-missing" }
    if ($configuredClientBuild -ge 947 -and $runtimeUsesRetailStartupConfig -and $prefer947PatchedDirectClient) {
        $runtimeHotArchiveParityMismatchIds = @(
            foreach ($archiveId in $runtimeHotArchiveIds947) {
                if (-not (Test-RuntimeArchiveMatchesSource -SourceCacheDir $runtimeCacheSourceDir -RuntimeCacheDir $runtimeCacheTargetDir -ArchiveId $archiveId)) {
                    $archiveId
                }
            }
        )
    }
    $runtimeClientManagedHotArchiveSet = $configuredClientBuild -ge 947 -and $runtimeUsesRetailStartupConfig -and $prefer947PatchedDirectClient -and $runtimeMissingHotArchiveIds.Count -eq 0 -and $runtimeHotMissingReferenceTableArchiveIds.Count -eq 0 -and $runtimeHotArchiveParityMismatchIds.Count -eq 0
    Write-LaunchTrace ("runtime cache sync mode={0} sourceCount={1} runtimeFileCount={2} runtimeArchiveCount={3} hotStubCount={4} hotStubArchives={5} hotMissingCount={6} hotMissingReferenceCount={7} hotParityMismatchCount={8}" -f $runtimeSyncMode, $runtimeSourceFiles.Count, $runtimeTargetFiles.Count, $runtimeTargetArchiveCount.Count, $runtimeHotStubArchiveIds.Count, (($runtimeHotStubArchiveIds | ForEach-Object { [string]$_ }) -join ","), $runtimeMissingHotArchiveIds.Count, $runtimeHotMissingReferenceTableArchiveIds.Count, $runtimeHotArchiveParityMismatchIds.Count)
    $runtimeCacheSyncParameters = @{
        SourceCacheDir = $runtimeCacheSourceDir
        RuntimeCacheDir = $runtimeCacheTargetDir
        SummaryOutput  = $runtimeCacheSyncSummary
        NoOutput       = $true
    }
    if ($runtimeAliasSeedingEnabled) {
        $runtimeCacheSyncParameters["SeedCorePrefixedAliases"] = $true
    }
    # Now that the direct-patched 947 retail-shaped path serves live retail
    # logged-out reference tables directly, tearing down the runtime hot archive
    # set on every launch only leaves the client with freshly recreated 12 KB
    # placeholders and no path forward beyond the splash screen. Prefer syncing
    # the staged hot archives into ProgramData and only quarantine them when a
    # future targeted diagnostic explicitly requests it.
    $runtimeForceRetailRefreshHotArchiveSet = $false
    $runtimeShouldPreserveHotArchiveSet = (
        $runtimeForceRetailRefreshHotArchiveSet -or
        ((-not $prefer947PatchedDirectClient) -and (-not $runtimeUsesRetailStartupConfig) -and -not $RepairRuntimeHotCache.IsPresent)
    )
    if ($runtimeShouldPreserveHotArchiveSet) {
        $runtimeCacheSyncParameters["SkipJs5Archives"] = $runtimeHotArchiveIds947
        if ((-not $runtimeClientManagedHotArchiveSet) -and (-not $runtimeForceRetailRefreshHotArchiveSet)) {
            $runtimeCacheSyncParameters["ValidateSkippedArchives"] = $true
        }
    }
    if (
        $runtimeShouldPreserveHotArchiveSet -and
        -not $runtimeClientManagedHotArchiveSet -and
        -not $runtimeForceRetailRefreshHotArchiveSet -and
        $runtimeHotStubArchiveIds.Count -gt 0
    ) {
        $runtimeCacheSyncParameters["RescueSkippedBootstrapStubs"] = $true
    }
    if (-not $runtimePromoteToFullSync) {
        $runtimeCacheSyncParameters["SeedMissingOnly"] = $true
    }
    try {
        & $runtimeCacheSyncScript @runtimeCacheSyncParameters
    } catch {
        Write-LaunchTrace ("runtime cache sync failed but launch will continue: {0}" -f $_.Exception.Message)
    }
    if (Test-Path $runtimeCacheSyncSummary) {
        $runtimeCacheSyncResult = Get-Content -Path $runtimeCacheSyncSummary -Raw | ConvertFrom-Json
        $runtimeCacheSyncResult | Add-Member -NotePropertyName SyncMode -NotePropertyValue $runtimeSyncMode -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName RuntimeSourceCount -NotePropertyValue $runtimeSourceFiles.Count -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName RuntimeTargetCountBefore -NotePropertyValue $runtimeTargetFiles.Count -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName RuntimeTargetArchiveCountBefore -NotePropertyValue $runtimeTargetArchiveCount.Count -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName RuntimeAliasSeedingEnabled -NotePropertyValue $runtimeAliasSeedingEnabled -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName HotStubArchiveIdsBefore -NotePropertyValue @($runtimeHotStubArchiveIds) -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName MissingHotArchiveIdsBefore -NotePropertyValue @($runtimeMissingHotArchiveIds) -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName HotMissingReferenceTableArchiveIdsBefore -NotePropertyValue @($runtimeHotMissingReferenceTableArchiveIds) -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName HotArchiveParityMismatchIdsBefore -NotePropertyValue @($runtimeHotArchiveParityMismatchIds) -Force
        $runtimeCopiedHotArchiveIds = @(
            @($runtimeCacheSyncResult.CopiedArchives) |
                Where-Object { $runtimeHotArchiveIds947 -contains [int]$_ } |
                ForEach-Object { [int]$_ } |
                Select-Object -Unique
        )
        $runtimeCacheSyncResult | Add-Member -NotePropertyName CopiedHotArchiveIds -NotePropertyValue @($runtimeCopiedHotArchiveIds) -Force
        Write-LaunchTrace ("runtime cache sync mode={0} rescued={1} copied={2} copiedTargets={3} unchanged={4} skipped={5} skipArchives={6}" -f $runtimeSyncMode, $runtimeCacheSyncResult.RescuedCount, $runtimeCacheSyncResult.CopiedCount, $runtimeCacheSyncResult.CopiedTargetCount, $runtimeCacheSyncResult.UnchangedCount, $runtimeCacheSyncResult.SkippedCount, (($runtimeCacheSyncResult.SkipJs5Archives | ForEach-Object { [string]$_ }) -join ","))
    } else {
        Write-LaunchTrace "runtime cache sync summary missing"
    }
}

$runtimeShouldAutoRepairHotCache947 = $configuredClientBuild -ge 947 -and (
    ($runtimeForceRetailRefreshHotArchiveSet -and $runtimeShouldPreserveHotArchiveSet) -or
    ($runtimeShouldPreserveHotArchiveSet -and -not $runtimeClientManagedHotArchiveSet -and ($runtimeHotStubArchiveIds.Count -gt 0 -or $runtimeHotMissingReferenceTableArchiveIds.Count -gt 0))
)
if ($runtimeShouldAutoRepairHotCache947 -and -not $RepairRuntimeHotCache.IsPresent) {
    $runtimeAutoRepairReason = if ($runtimeForceRetailRefreshHotArchiveSet) {
        "auto-retail-hot-archive-refresh"
    } elseif ($runtimeHotMissingReferenceTableArchiveIds.Count -gt 0) {
        "auto-hot-missing-reference-table-quarantine"
    } else {
        "auto-hot-stub-quarantine"
    }
}
$runtimeHotCacheRepairArchiveIds = if ($RepairRuntimeHotCache.IsPresent) {
    @($runtimeHotArchiveIds947)
} elseif ($runtimeForceRetailRefreshHotArchiveSet) {
    @($runtimeHotArchiveIds947)
} elseif ($runtimeShouldAutoRepairHotCache947) {
    @(
        @($runtimeHotStubArchiveIds) +
        @($runtimeHotMissingReferenceTableArchiveIds) |
            Sort-Object -Unique
    )
} else {
    @()
}
Write-LaunchTrace ("runtime hot cache repair decision mode={0} archiveCount={1} archives={2}" -f $(if ($RepairRuntimeHotCache.IsPresent) { "manual" } elseif (-not [string]::IsNullOrWhiteSpace($runtimeAutoRepairReason)) { $runtimeAutoRepairReason } else { "skip" }), $runtimeHotCacheRepairArchiveIds.Count, (($runtimeHotCacheRepairArchiveIds | ForEach-Object { [string]$_ }) -join ","))

if (
    -not $runtimeCacheSyncSkippedEffective -and
    ($RepairRuntimeHotCache.IsPresent -or $runtimeShouldAutoRepairHotCache947) -and
    -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and
    (Test-Path $runtimeHotCacheRepairScript) -and
    $runtimeHotCacheRepairArchiveIds.Count -gt 0
) {
    Write-LaunchTrace ("runtime hot cache repair start runtime={0}" -f (Join-Path $env:ProgramData "Jagex\\RuneScape"))
    $runtimeRepairArgs = @{
        RuntimeCacheDir = (Join-Path $env:ProgramData "Jagex\\RuneScape")
        ArchiveIds = $runtimeHotCacheRepairArchiveIds
        IncludeAuxiliaryFiles = $true
        SummaryOutput = $runtimeHotCacheRepairSummary
        NoOutput = $true
    }
    if ($configuredClientBuild -ge 947) {
        $runtimeRepairArgs["IncludeCorePrefixedAliases"] = $true
    }
    & $runtimeHotCacheRepairScript @runtimeRepairArgs
    if (Test-Path $runtimeHotCacheRepairSummary) {
        $runtimeHotCacheRepairResult = Get-Content -Path $runtimeHotCacheRepairSummary -Raw | ConvertFrom-Json
        Write-LaunchTrace ("runtime hot cache repair moved={0} missing={1}" -f $runtimeHotCacheRepairResult.MovedCount, $runtimeHotCacheRepairResult.MissingCount)
    } else {
        Write-LaunchTrace "runtime hot cache repair summary missing"
    }
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

    $environmentCommands = @('set "JAVA_TOOL_OPTIONS=-XX:TieredStopAtLevel=1"')
    if ($configuredClientBuild -ge 947) {
        $environmentCommands += 'set "OPENNXT_ENABLE_RETAIL_RAW_CHECKSUM_PASSTHROUGH=1"'
        if (-not $AllowRetailJs5Upstream) {
            $environmentCommands += 'set "OPENNXT_ENABLE_RETAIL_LOGGED_OUT_JS5_PASSTHROUGH=1"'
        } else {
            $environmentCommands += 'set "OPENNXT_ENABLE_RETAIL_LOGGED_OUT_JS5_PASSTHROUGH=0"'
        }
    }
    if ($DisableChecksumOverride) {
        $environmentCommands += 'set "OPENNXT_DISABLE_CHECKSUM_OVERRIDE=1"'
    }

    $serverCommandInstall = '{0} && "{1}" {2}' -f ($environmentCommands -join " && "), $openNxtBat, ($serverArgs -join " ")
    $serverCommandFallback = '{0} && call "{1}" --no-daemon --console=plain run --args=""run-server""' -f ($environmentCommands -join " && "), $gradleBat
    $serverLaunchMode = if (Test-InstalledServerEntrypoint) { "installDist" } else { "gradleRunFallback" }
    $serverCommand = if ($serverLaunchMode -eq "installDist") { $serverCommandInstall } else { $serverCommandFallback }

    function Start-ServerWrapperProcess {
        param([string]$Command)

        return Start-Process -FilePath $env:ComSpec `
            -ArgumentList @("/c", $Command) `
            -WorkingDirectory $root `
            -RedirectStandardOutput $serverOut `
            -RedirectStandardError $serverErr `
            -PassThru
    }

    $wrapper = Start-ServerWrapperProcess -Command $serverCommand
    Write-LaunchTrace "started server wrapper pid=$($wrapper.Id) mode=$serverLaunchMode"

    $serverPid = $null
    $serverPorts = @($configuredHttpPort, $configuredGameBackendPort)
    try {
        Write-LaunchTrace ("waiting for server ports={0} timeout={1}s mode={2}" -f ($serverPorts -join ","), $StartupTimeoutSeconds, $serverLaunchMode)
        if (-not (Wait-ListeningPorts -Ports $serverPorts -TimeoutSeconds $StartupTimeoutSeconds)) {
            Write-ServerStartupDiagnostics -WrapperProcess $wrapper -Ports $serverPorts -Prefix ("server ports wait failed mode={0}" -f $serverLaunchMode)
            $stderrRaw = if (Test-Path $serverErr) { Get-Content $serverErr -Raw -ErrorAction SilentlyContinue } else { "" }
            $installStartupBroken = $serverLaunchMode -eq "installDist" -and (
                $stderrRaw -match 'NoClassDefFoundError' -or
                $stderrRaw -match 'ClassNotFoundException' -or
                $stderrRaw -match 'ReflectKotlinClassFinder'
            )

            if ($installStartupBroken) {
                Write-LaunchTrace "installed server startup failed; retrying gradle run fallback"
                try {
                    taskkill /PID $wrapper.Id /F | Out-Null
                } catch {}
                Remove-Item $serverOut, $serverErr -ErrorAction SilentlyContinue
                $serverLaunchMode = "gradleRunFallback"
                $wrapper = Start-ServerWrapperProcess -Command $serverCommandFallback
                Write-LaunchTrace "started server wrapper pid=$($wrapper.Id) mode=$serverLaunchMode"
                $fallbackTimeoutSeconds = [Math]::Max($StartupTimeoutSeconds, 180)
                Write-LaunchTrace ("waiting for server ports={0} timeout={1}s mode={2}" -f ($serverPorts -join ","), $fallbackTimeoutSeconds, $serverLaunchMode)
                if (-not (Wait-ListeningPorts -Ports $serverPorts -TimeoutSeconds $fallbackTimeoutSeconds)) {
                    Write-ServerStartupDiagnostics -WrapperProcess $wrapper -Ports $serverPorts -Prefix ("server ports wait failed mode={0}" -f $serverLaunchMode)
                    throw "Timed out waiting for OpenNXT server ports $configuredHttpPort and $configuredGameBackendPort after fallback startup"
                }
            } else {
                throw "Timed out waiting for OpenNXT server ports $configuredHttpPort and $configuredGameBackendPort after $StartupTimeoutSeconds seconds"
            }
        }
        Write-LaunchTrace "server ports ready"

        $serverPid = Get-ListeningProcessIds -Ports $serverPorts | Select-Object -First 1
        if ($null -eq $serverPid) {
            Write-LaunchTrace ("server pid unresolved mode={0} listenerSnapshot={1}" -f $serverLaunchMode, (Get-ListeningPortSnapshot -Ports $serverPorts))
        } else {
            Write-LaunchTrace "server pid=$serverPid mode=$serverLaunchMode"
        }
    } catch {
        Write-ServerStartupDiagnostics -WrapperProcess $wrapper -Ports $serverPorts -Prefix "server startup exception"
        Write-LaunchTrace ("server startup exception message={0}" -f $_.Exception.Message)
        if (-not [string]::IsNullOrWhiteSpace($_.ScriptStackTrace)) {
            Write-LaunchTrace ("server startup exception stack={0}" -f $_.ScriptStackTrace.Replace([Environment]::NewLine, " <NL> "))
        }
        throw
    }

    if ($configuredClientBuild -ge 947 -and $use947RetailConfigHost -and $script:UseContentTlsRoute) {
        $startupConfigContent = Get-947StartupConfigContent -ConfigUrl $effectiveLaunchArg -HttpPort $configuredHttpPort
        if (-not [string]::IsNullOrWhiteSpace($startupConfigContent)) {
            $startupConfigSnapshotReady = Save-947StartupConfigSnapshot -ConfigContent $startupConfigContent -OutputPath $startupConfigSnapshotPath
            $startupRouteHosts = @(Get-947StartupRouteHostsFromConfigContent -ConfigContent $startupConfigContent)
            $enable947StartupResolveRedirects = $configuredClientBuild -ge 947 -and $use947RetailConfigHost -and $script:UseContentTlsRoute -and $Force947StartupRouteRedirects
            if ($enable947StartupResolveRedirects) {
                # Match the last clean contained direct baseline: explicit
                # startup-route experiments must redirect the content bootstrap
                # host and the secure world/lobby fleet locally together.
                $startupRedirectHosts = @(
                    @(
                        (@($startupRouteHosts) | Where-Object { Test-947SecureStartupRedirectHost -HostName $_ }) +
                            @(Get-947SecureRetailWorldFleetHosts)
                    ) |
                        Where-Object { $_ -notin @("localhost", "127.0.0.1", "::1", "rs.config.runescape.com") } |
                        Select-Object -Unique
                )
                $script:ConfiguredTlsExtraMitmHosts = @(
                    @(
                        $script:ConfiguredTlsExtraMitmHosts +
                            $startupRedirectHosts
                    ) |
                        Select-Object -Unique
                )
                $resolveRedirectSpecs = @(
                    @(
                        $resolveRedirectSpecs +
                            ($startupRedirectHosts | ForEach-Object { "{0}={1}" -f $_, $defaultMitmPrimaryHost })
                    ) |
                        Select-Object -Unique
                )
                Write-LaunchTrace ("947 startup secure resolve redirects={0}" -f ($resolveRedirectSpecs -join ","))
            } else {
                # 947 win64 splash bootstrap must stay on the retail startup
                # world/content/lobby hosts until login. Redirecting those
                # fetched route hosts back to localhost is only for explicit
                # forced-startup experiments; the default path keeps them
                # retail-shaped through the login transition.
                $resolveRedirectSpecs = @($resolveRedirectSpecs | Select-Object -Unique)
                Write-LaunchTrace "947 startup secure resolve redirects=<disabled-default>"
            }
        } else {
            Write-LaunchTrace "947 startup secure resolve redirects=<config-fetch-failed>"
        }
    }

    if ($configuredClientBuild -ge 947 -and -not $use947RetailConfigHost) {
        $startupConfigContent = Get-947StartupConfigContent -ConfigUrl $effectiveLaunchArg -HttpPort $configuredHttpPort
        if (-not [string]::IsNullOrWhiteSpace($startupConfigContent)) {
            if (Save-947StartupConfigSnapshot -ConfigContent $startupConfigContent -OutputPath $startupConfigSnapshotPath) {
                $startupConfigSnapshotReady = $true
                $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSnapshotPath" -Value $startupConfigSnapshotPath
                Write-LaunchTrace ("947 startup config snapshot={0}" -f $startupConfigSnapshotPath)
            }
            if ($script:UseContentTlsRoute) {
                $script:ConfiguredTlsExtraMitmHosts = @(Get-947StartupWorldMitmHostsFromConfigContent -ConfigContent $startupConfigContent)
            }
            # 947 must keep the config snapshot's world/content/lobby hosts
            # retail-shaped through the application-resource splash bootstrap.
            # Redirecting those startup route hosts to localhost here recreates
            # the reference-table loop before the login screen.
            $resolveRedirectSpecs = @($resolveRedirectSpecs | Select-Object -Unique)
        } else {
            Write-LaunchTrace "947 startup config snapshot=<fetch-failed>"
        }
        $script:Effective947StartupConfigHost = Get-UriHostName -Value $effectiveLaunchArg
        $clientArgs = @($effectiveLaunchArg)
    }
    if ($configuredClientBuild -ge 947 -and $script:UseContentTlsRoute) {
        if ($script:ConfiguredTlsExtraMitmHosts.Count -gt 0) {
            Write-LaunchTrace ("947 startup world MITM hosts={0}" -f ($script:ConfiguredTlsExtraMitmHosts -join ","))
        } else {
            Write-LaunchTrace "947 startup world MITM hosts=<none>"
        }
    }
} finally {
    if ($proxyConfigModified) {
        if ($proxyConfigExists) {
            [System.IO.File]::WriteAllText($proxyConfigPath, $proxyConfigOriginalContent)
        } else {
            Remove-Item $proxyConfigPath -Force -ErrorAction SilentlyContinue
        }
    }
}

$tlsTrustSetup = $null
if ($script:UseContentTlsRoute) {
    $tlsTrustSetup = Ensure-CanonicalMitmTrust -LobbyHost $script:ConfiguredMitmLobbyHost
    $script:CanonicalMitmTrustState = $tlsTrustSetup.TrustState
}

Write-LaunchTrace "starting lobby proxy"
Start-LobbyProxy
if (-not $script:EffectiveBypassGameProxy) {
    Write-LaunchTrace "starting game proxy"
    Start-GameProxy
}
Write-LaunchTrace "proxy launch scripts returned"

$watchdog = $null
$proxyPorts = if ($script:EffectiveBypassGameProxy) { @(443) } else { @(443, $configuredGamePort) }
if (-not (Wait-ListeningPorts -Ports $proxyPorts -TimeoutSeconds $ProxyStartupTimeoutSeconds)) {
    throw "Timed out waiting for proxy ports $($proxyPorts -join ', ') after $ProxyStartupTimeoutSeconds seconds"
}
Write-LaunchTrace "proxy ports ready"
Sync-ContentHostsOverride

if (-not $DisableWatchdog) {
    Remove-Item $watchdogOut, $watchdogErr -ErrorAction SilentlyContinue
    $watchdogArgs = @(
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ('"{0}"' -f $watchdogScript),
        "-CheckIntervalSeconds",
        "2"
    )
    if ($script:EffectiveBypassGameProxy) {
        $watchdogArgs += "-BypassGameProxy"
    }
    if ($script:UseLobbyTlsPassthroughProxy) {
        $watchdogArgs += "-LobbyTlsPassthrough"
    }
    if ($AllowRetailJs5Upstream) {
        $watchdogArgs += "-AllowRetailJs5Upstream"
    }
    $watchdog = Start-Process -FilePath $powershellExe `
        -ArgumentList $watchdogArgs `
        -WorkingDirectory $root `
        -RedirectStandardOutput $watchdogOut `
        -RedirectStandardError $watchdogErr `
        -PassThru
    Write-LaunchTrace "watchdog pid=$($watchdog.Id)"
}

$lobbyProxyPid = Get-ListeningProcessIds -Ports @(443) | Select-Object -First 1
$gameProxyPid = if ($script:EffectiveBypassGameProxy) { $null } else { Get-ListeningProcessIds -Ports @($configuredGamePort) | Select-Object -First 1 }
Write-LaunchTrace "lobbyProxyPid=$lobbyProxyPid gameProxyPid=$gameProxyPid"

$stagedRuneScapeWrapper = $null
$useRuneScapeWrapper = $false
$selectedClientDir = if ($effectiveUseOriginalClient) { $originalClientDir } else { $clientDir }
$selectedClientExe = if ($effectiveUseOriginalClient) { $originalClientExe } else { $clientExe }
$selectedRuneScapeWrapper = Join-Path $selectedClientDir "RuneScape.exe"
$selectedChildExe = Join-Path $selectedClientDir "rs2client.exe"
$runtimeSyncLocalDir = $selectedClientDir
if (
    $configuredClientBuild -ge 947 -and
    -not [string]::IsNullOrWhiteSpace($resolvedDownloadMetadataSource) -and
    @("original", "patched", "compressed") -contains $resolvedDownloadMetadataSource
) {
    $resolvedRuntimeSyncDir = Join-Path $root ("data\\clients\\{0}\\win64c\\{1}" -f $configuredClientBuild, $resolvedDownloadMetadataSource)
    if (Test-Path $resolvedRuntimeSyncDir) {
        $runtimeSyncLocalDir = $resolvedRuntimeSyncDir
    }
}
if ($configuredClientBuild -ge 947 -and -not $UsePatchedLauncher -and -not $prefer947PatchedDirectClient) {
    $stagedRuneScapeWrapper = Sync-InstalledRuneScapeWrapper -ClientDirectory $selectedClientDir
    if ([string]::IsNullOrWhiteSpace($stagedRuneScapeWrapper) -or -not (Test-Path $stagedRuneScapeWrapper)) {
        if (Test-Path $selectedRuneScapeWrapper) {
            $stagedRuneScapeWrapper = $selectedRuneScapeWrapper
        }
    }
    # The wrapper path remains available for explicit experiments, but the
    # default 947 live path stays on a single direct rs2client launch family.
    $useRuneScapeWrapper = -not [string]::IsNullOrWhiteSpace($stagedRuneScapeWrapper) -and (Test-Path $stagedRuneScapeWrapper)
}
$clientLaunchPath = if ($useRuneScapeWrapper) {
    $stagedRuneScapeWrapper
} else {
    $selectedClientExe
}
$clientWorkingDirectory = $selectedClientDir
$effectiveClientArgs = @($clientArgs)
$directPatchInlinePatchOffsets = @()
$directPatchJumpBypassSpecs = @()
$directPatchExtraArgs = @()
$directPatchLaunchSummary = $null
$installedRuntimeSyncResult = $null
$wrapperExtraArgs = @()
$wrapperInlinePatchOffsets = @()
$wrapperJumpBypassSpecs = @()
$useDirectPatchedRs2Client = -not $UsePatchedLauncher -and
    -not $useRuneScapeWrapper -and
    $configuredClientBuild -ge 947 -and
    [string]::Equals((Split-Path -Leaf $clientLaunchPath), "rs2client.exe", [System.StringComparison]::OrdinalIgnoreCase)
$autoManageGraphicsCompat = $AutoSwitchGraphicsCompat.IsPresent -or
    (($useRuneScapeWrapper -or $useDirectPatchedRs2Client) -and $configuredClientBuild -ge 947)
if (
    $configuredClientBuild -ge 947 -and
    $useRuneScapeWrapper -and
    -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and
    (Test-Path $installedRuntimeSyncTool)
) {
    Write-LaunchTrace ("installed runtime sync start local={0} installed={1}" -f $runtimeSyncLocalDir, (Join-Path $env:ProgramData "Jagex\\launcher"))
    $installedRuntimeSyncArgs = @(
        $installedRuntimeSyncTool,
        "--config-url",
        $effectiveLaunchArg,
        "--local-dir",
        $runtimeSyncLocalDir,
        "--installed-dir",
        (Join-Path $env:ProgramData "Jagex\\launcher"),
        "--summary-output",
        $installedRuntimeSyncSummary,
        "--timeout-seconds",
        "30"
    )
    if (-not [string]::IsNullOrWhiteSpace($startupConfigSnapshotPath) -and (Test-Path $startupConfigSnapshotPath)) {
        $installedRuntimeSyncArgs += "--config-file"
        $installedRuntimeSyncArgs += $startupConfigSnapshotPath
    }
    $installedRuntimeSyncJson = & python @installedRuntimeSyncArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Installed runtime sync failed with exit code $LASTEXITCODE."
    }
    if (-not [string]::IsNullOrWhiteSpace($installedRuntimeSyncJson)) {
        $installedRuntimeSyncResult = $installedRuntimeSyncJson | ConvertFrom-Json
    } elseif (Test-Path $installedRuntimeSyncSummary) {
        $installedRuntimeSyncResult = Get-Content -Path $installedRuntimeSyncSummary -Raw | ConvertFrom-Json
    }
    if ($null -ne $installedRuntimeSyncResult) {
        Write-LaunchTrace ("installed runtime sync localReady={0} wrapperLaunchReady={1} wrapperLocalChildOverrideReady={2} wrapperInstalledChildReady={3} installedReadyAfter={4} copied={5} failed={6}" -f $installedRuntimeSyncResult.localReady, $installedRuntimeSyncResult.wrapperLaunchReady, $installedRuntimeSyncResult.wrapperLocalChildOverrideReady, $installedRuntimeSyncResult.wrapperInstalledChildReady, $installedRuntimeSyncResult.installedReadyAfter, $installedRuntimeSyncResult.copiedCount, $installedRuntimeSyncResult.failedCount)
    } else {
        Write-LaunchTrace "installed runtime sync summary missing"
    }
    if (
        $null -ne $installedRuntimeSyncResult -and
        -not [bool]$installedRuntimeSyncResult.wrapperLaunchReady
    ) {
        throw "Installed runtime sync refused to continue because neither the staged local 947 client family nor the already-installed wrapper child runtime is launch-ready."
    }
    if ($null -ne $installedRuntimeSyncResult -and -not [bool]$installedRuntimeSyncResult.installedReadyAfter) {
        throw "Installed runtime sync completed but ProgramData runtime files still do not match the live manifest."
    }
}
if ($configuredClientBuild -ge 947 -and $script:UseContentTlsRoute -and -not $script:CanWriteHostsFile) {
    # 947 splash startup should not inject a localhost rs.config leg. The staged
    # startup snapshot is enough, and the extra redirect recreates a bogus
    # raw-bootstrap branch ahead of the secure content handshake.
}
$startupLauncherToken947 = "A234"
if ($configuredClientBuild -ge 947 -and [string]::IsNullOrWhiteSpace($startupConfigContent)) {
    $startupConfigContent = Get-947StartupConfigContent -ConfigUrl $effectiveLaunchArg -HttpPort $configuredHttpPort
}
$launcherPreferencesResult = $null
$graphicsDeviceResult = $null
$gpuPreferenceResult = $null
if ($autoManageGraphicsCompat -and ($useRuneScapeWrapper -or $useDirectPatchedRs2Client) -and (Test-Path $launcherPreferencesScript)) {
    $preferHighPerformanceGraphics = Test-RecentD3DDeviceRemoved -LogPaths @($directPatchStderr, $wrapperRewriteStderr)
    $effectiveGraphicsCompatibilityMode = $GraphicsCompatibilityMode
    if ([string]::IsNullOrWhiteSpace($effectiveGraphicsCompatibilityMode) -or $effectiveGraphicsCompatibilityMode -eq "auto") {
        $effectiveGraphicsCompatibilityMode = "true"
    }
    $effectiveGraphicsDevicePreference = $GraphicsDevicePreference
    if ([string]::IsNullOrWhiteSpace($effectiveGraphicsDevicePreference) -or $effectiveGraphicsDevicePreference -eq "auto") {
        # Keep 947 on the safer Intel/power-saving lane by default, but if the
        # previous run ended with D3D11 device removal then retry on the
        # discrete adapter instead of repeating the known-bad render path.
        $effectiveGraphicsDevicePreference = "power-saving"
        if ($preferHighPerformanceGraphics) {
            $effectiveGraphicsDevicePreference = "high-performance"
        }
    }
    $resolvedGraphicsDevice = "default"
    if ($configuredClientBuild -ge 947 -and (Test-Path $graphicsDeviceResolverScript)) {
        if ($effectiveGraphicsDevicePreference -eq "power-saving") {
            $graphicsDeviceJson = & $graphicsDeviceResolverScript -Preference "power-saving" -SummaryOutput $graphicsDeviceSummary
        } else {
            $graphicsDeviceJson = & $graphicsDeviceResolverScript -Preference $effectiveGraphicsDevicePreference -SummaryOutput $graphicsDeviceSummary
        }
        if (-not [string]::IsNullOrWhiteSpace($graphicsDeviceJson)) {
            $graphicsDeviceResult = $graphicsDeviceJson | ConvertFrom-Json
            if (-not [string]::IsNullOrWhiteSpace([string]$graphicsDeviceResult.SelectedGraphicsDevice)) {
                $resolvedGraphicsDevice = [string]$graphicsDeviceResult.SelectedGraphicsDevice
            }
        }
    }
    $launcherPreferenceParams = @{
        Compatibility = $effectiveGraphicsCompatibilityMode
        ClearDontAskAgain = $true
        SummaryOutput = $launcherPreferencesSummary
    }
    if ($configuredClientBuild -ge 947) {
        $launcherPreferenceParams.GraphicsDevice = $resolvedGraphicsDevice
    }
    $preferencesJson = & $launcherPreferencesScript @launcherPreferenceParams
    if (-not [string]::IsNullOrWhiteSpace($preferencesJson)) {
        $launcherPreferencesResult = $preferencesJson | ConvertFrom-Json
    }
}
if ($configuredClientBuild -ge 947 -and (Test-Path $windowsGpuPreferenceScript)) {
    $gpuTargets = @(
        $clientLaunchPath
        $installedGameClientExe
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
    if ($gpuTargets.Count -gt 0) {
        $preferHighPerformanceGraphics = Test-RecentD3DDeviceRemoved -LogPaths @($directPatchStderr, $wrapperRewriteStderr)
        # Keep 947 on the safer Windows GPU lane by default; the discrete-GPU
        # override has been correlated with CLOCK_WATCHDOG_TIMEOUT bugchecks.
        # If the previous run hit D3D11 device removal on that lane, retry on
        # the discrete adapter instead of pinning the failing config forever.
        $effectiveWindowsGpuPreference = $GraphicsDevicePreference
        if ([string]::IsNullOrWhiteSpace($effectiveWindowsGpuPreference) -or $effectiveWindowsGpuPreference -eq "auto") {
            $effectiveWindowsGpuPreference = "power-saving"
            if ($preferHighPerformanceGraphics) {
                $effectiveWindowsGpuPreference = "high-performance"
            }
        }
        if ($effectiveWindowsGpuPreference -eq "power-saving") {
            $gpuPreferenceJson = & $windowsGpuPreferenceScript -ExecutablePath $gpuTargets -Preference "power-saving" -SummaryOutput $gpuPreferenceSummary
        } else {
            $gpuPreferenceJson = & $windowsGpuPreferenceScript -ExecutablePath $gpuTargets -Preference $effectiveWindowsGpuPreference -SummaryOutput $gpuPreferenceSummary
        }
        if (-not [string]::IsNullOrWhiteSpace($gpuPreferenceJson)) {
            $gpuPreferenceResult = $gpuPreferenceJson | ConvertFrom-Json
        }
    }
}
if ($useRuneScapeWrapper) {
    Stop-WrapperLaunchArtifacts -WrapperExePath $clientLaunchPath | Out-Null
}
if ($UsePatchedLauncher) {
    if (-not (Test-Path $launcherExe)) {
        throw "Patched launcher not found at $launcherExe"
    }

    $clientLaunchPath = $launcherExe
    $clientWorkingDirectory = $launcherDir
    $effectiveClientArgs = @("--configURI", $effectiveLaunchArg)
} elseif ($useRuneScapeWrapper) {
    $clientWorkingDirectory = $selectedClientDir
    $effectiveClientArgs = @("--configURI=$effectiveLaunchArg")
    if ($configuredClientBuild -ge 947) {
        if (-not $DisableUseAngle.IsPresent) {
            $wrapperExtraArgs += "--useAngle"
        }
        if (-not $Disable947InlineNullReadPatches.IsPresent) {
            $wrapperInlinePatchOffsets += "0x590001"
            $wrapperInlinePatchOffsets += "0x590321"
            $wrapperInlinePatchOffsets += "0x5916c3"
            $wrapperInlinePatchOffsets += "0x5916f0"
            $wrapperInlinePatchOffsets += "0x591712"
            $wrapperInlinePatchOffsets += "0x591719"
            $wrapperInlinePatchOffsets += "0x5919e3"
            $wrapperInlinePatchOffsets += "0x591a10"
            $wrapperInlinePatchOffsets += "0x591a32"
            $wrapperInlinePatchOffsets += "0x591a39"
            $wrapperInlinePatchOffsets += "0x594d61"
        }
        if (-not $Disable947JumpBypassGuards.IsPresent) {
        # With 0x590cf4 removed, the client faults immediately at 0x59002d
        # (mov rdx, qword ptr [rbx+0x10]) unless we keep this early null-deref
        # bypass active.
        $wrapperJumpBypassSpecs += "0x59002d:0x5900a5"
        # FUN_140590220 can stale out on state==1 before it re-runs the normal
        # 0x7710/0x7734/0x77d8 readiness checks. Keep that fast path only when the
        # normal-path buffers are populated; otherwise fall back into the original
        # compare/enqueue path.
        $wrapperJumpBypassSpecs += "0x5902d5:0x5903bd"
        # Some contained 947 runs still reach the master-table entry lookup
        # before owner+0x30d0 is populated, or with an out-of-range entry
        # index that would fall into the bad absolute-read fallback at 0x590c72.
        # Guard that lookup, but keep the real in-range table path live.
        $wrapperJumpBypassSpecs += "0x590c58:0x590c81"
            # After `/ms` succeeds, some login-path packets still reach
            # FUN_1402ab680 with a sentinel param_2 whose +0x8 field is null.
            # Guard that stale update and return through the normal epilogue
            # instead of AV'ing at 0x2ab6ad on [rsi+0x40].
            $wrapperJumpBypassSpecs += "0x2ab698:0x2ab7f7"
            # Once contained lobby bootstrap completes, some runs open the
            # follow-on world socket and immediately enter FUN_140369980 with a
            # poisoned `*param_1` base. Guard the `[r10+0x18]` walk and fall
            # back to a conservative zero result instead of AV'ing before any
            # world payload is sent.
            $wrapperJumpBypassSpecs += "0x3699b2:0x3699f2"
            # Some contained sign-in runs now advance into FUN_1407a3ad0 with
            # stale vector-slot bookkeeping and then AV on the direct slot
            # write path. Force the function's own slow-path allocator/helper.
            $wrapperJumpBypassSpecs += "0x7a3bc2:0x7a3bff"
        }
    }
    if ($normalizedExtraClientArgs.Count -gt 0) {
        $effectiveClientArgs += $normalizedExtraClientArgs
    }
}
$shouldUse947DirectParamPairArgs = $false
if ($shouldUse947DirectParamPairArgs) {
    # Direct patched 947 launches stay on the single config-URL startup family.
    # Converting them to raw param-pair argv recreates the short-lived startup
    # branch that dies before the healthy splash/login path.
    $paramPairArgs947 = @(Convert-947StartupConfigToParamPairArgs -ConfigContent $startupConfigContent -LauncherToken $startupLauncherToken947)
    if ($paramPairArgs947.Count -gt 0) {
        $effectiveClientArgs = @($paramPairArgs947)
        if ($normalizedExtraClientArgs.Count -gt 0) {
            $effectiveClientArgs += $normalizedExtraClientArgs
        }
    }
}
if ($configuredClientBuild -ge 947 -and (Test-Path $selectedChildExe)) {
    if (-not $Disable947InlineNullReadPatches.IsPresent) {
        $directPatchInlinePatchOffsets += "0x590001"
        $directPatchInlinePatchOffsets += "0x590321"
        $directPatchInlinePatchOffsets += "0x5916c3"
        $directPatchInlinePatchOffsets += "0x5916f0"
        $directPatchInlinePatchOffsets += "0x591712"
        $directPatchInlinePatchOffsets += "0x591719"
        $directPatchInlinePatchOffsets += "0x5919e3"
        $directPatchInlinePatchOffsets += "0x591a10"
        $directPatchInlinePatchOffsets += "0x591a32"
        $directPatchInlinePatchOffsets += "0x591a39"
        $directPatchInlinePatchOffsets += "0x594d61"
    }
    if (-not $Disable947JumpBypassGuards.IsPresent) {
        # Keep the early FUN_14058fed0 null-deref guard active; removing it moves
        # the fault straight onto 0x59002d before the client can reach the splash.
        $directPatchJumpBypassSpecs += "0x59002d:0x5900a5"
        $directPatchJumpBypassSpecs += "0x5902d5:0x5903bd"
        # Some contained 947 runs still reach the master-table entry lookup before
        # owner+0x30d0 is populated, or with an out-of-range entry index that
        # would fall into the bad absolute-read fallback at 0x590c72. Guard that
        # lookup, but keep the real in-range table path live.
        $directPatchJumpBypassSpecs += "0x590c58:0x590c81"
        # After `/ms` succeeds, some login-path packets still reach
        # FUN_1402ab680 with a sentinel param_2 whose +0x8 field is null.
        # Guard that stale update and return through the normal epilogue
        # instead of AV'ing at 0x2ab6ad on [rsi+0x40].
        $directPatchJumpBypassSpecs += "0x2ab698:0x2ab7f7"
        # Once contained lobby bootstrap completes, some runs open the
        # follow-on world socket and immediately enter FUN_140369980 with a
        # poisoned `*param_1` base. Guard the `[r10+0x18]` walk and fall back
        # to a conservative zero result instead of AV'ing before any world
        # payload is sent.
        $directPatchJumpBypassSpecs += "0x3699b2:0x3699f2"
        # Some contained sign-in runs now advance into FUN_1407a3ad0 with
        # stale vector-slot bookkeeping and then AV on the direct slot write
        # path. Force the function's own slow-path allocator/helper.
        $directPatchJumpBypassSpecs += "0x7a3bc2:0x7a3bff"
    }
}

$clientStartArgs = @{
    FilePath = $clientLaunchPath
    ArgumentList = @($effectiveClientArgs | ForEach-Object { Quote-ProcessArgument $_ })
    WorkingDirectory = $clientWorkingDirectory
    PassThru = $true
}

if ($CaptureConsole -and -not $UsePatchedLauncher) {
    $clientStartArgs.RedirectStandardOutput = $clientStdout
    $clientStartArgs.RedirectStandardError = $clientStderr
}

Write-LaunchTrace "starting client"
$graphicsHelperResult = $null
$resolvedClientPid = $null
$wrapperRewriteHelper = $null
$wrapperFallbackToDirectPatched = $false
$wrapperFallbackReason = $null
$wrapperAcceptedInstalledRuntimeChild = $false
$directPatchMonitorSeconds = [Math]::Max(300, $StartupTimeoutSeconds)

if ($useDirectPatchedRs2Client -and (Test-Path $directPatchTool)) {
    $directLaunch = Invoke-DirectPatchedLiveLaunch `
        -ClientExePath $clientLaunchPath `
        -WorkingDirectory $clientWorkingDirectory `
        -ClientArgumentList $effectiveClientArgs `
        -SummaryPath $directPatchSummary `
        -TracePath $directPatchTrace `
        -StartupHookOutputPath $directPatchStartupHookOutput `
        -DirectPatchToolPath $directPatchTool `
        -WorkspaceRoot $root `
        -RsaConfigPath $rsaConfigPath `
        -MonitorSeconds $directPatchMonitorSeconds `
        -InlinePatchOffsets $directPatchInlinePatchOffsets `
        -JumpBypassSpecs $directPatchJumpBypassSpecs `
        -DirectPatchExtraArgs $directPatchExtraArgs `
        -RedirectSpecs $resolveRedirectSpecs
    $directPatchLaunchSummary = $directLaunch.Summary
    $resolvedClientPid = $directLaunch.ResolvedClientPid
    $client = $directLaunch.Client
    $bootstrapClient = $directLaunch.BootstrapClient
} elseif ($useRuneScapeWrapper -and (Test-Path $wrapperRewriteTool)) {
    if (Test-Path $wrapperRewriteSummary) {
        Remove-Item $wrapperRewriteSummary -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $wrapperRewriteStdout, $wrapperRewriteStderr -Force -ErrorAction SilentlyContinue

    $rewriteArgs = @(
        $wrapperRewriteTool,
        "--wrapper-exe",
        $clientLaunchPath,
        "--config-uri",
        $effectiveLaunchArg,
        "--trace-output",
        $wrapperRewriteTrace,
        "--summary-output",
        $wrapperRewriteSummary,
        "--child-hook-output",
        $wrapperRewriteChildHookOutput
    )
    if ($configuredClientBuild -ge 947) {
        $rewriteArgs += "--rewrite-scope"
        $rewriteArgs += "all"
        $rewriteArgs += "--child-hook-duration-seconds"
        $rewriteArgs += "120"
        if ($startupConfigSnapshotReady -and (Test-Path $startupConfigSnapshotPath)) {
            $rewriteArgs += "--rewrite-config-file"
            $rewriteArgs += $startupConfigSnapshotPath
        }
        $wrapperLocalChildOverrideReady = (Test-Path $selectedChildExe)
        if ($null -ne $installedRuntimeSyncResult) {
            $wrapperLocalChildOverrideReady = $wrapperLocalChildOverrideReady -and [bool]$installedRuntimeSyncResult.wrapperLocalChildOverrideReady
        }
        if ($wrapperLocalChildOverrideReady) {
            $rewriteArgs += "--child-exe-override"
            $rewriteArgs += $selectedChildExe
        }
        $acceptedChildRefreshReady = $null -ne $installedRuntimeSyncResult -and
            [bool]$installedRuntimeSyncResult.wrapperLocalChildOverrideReady -and
            [bool]$installedRuntimeSyncResult.installedReadyAfter
        if ($acceptedChildRefreshReady -and -not [string]::IsNullOrWhiteSpace($installedGameClientExe) -and (Test-Path $installedGameClientExe)) {
            $rewriteArgs += "--accepted-child-exe"
            $rewriteArgs += $installedGameClientExe
        }
    }
    if (Test-Path $rsaConfigPath) {
        $rewriteArgs += "--rsa-config"
        $rewriteArgs += $rsaConfigPath
        if ($configuredClientBuild -ge 947 -and (Test-Path $originalClientExe)) {
            $rewriteArgs += "--js5-rsa-source-exe"
            $rewriteArgs += $originalClientExe
        }
    }
    foreach ($wrapperExtraArg in $wrapperExtraArgs) {
        $rewriteArgs += "--wrapper-extra-arg=$wrapperExtraArg"
    }
    foreach ($wrapperInlinePatchOffset in $wrapperInlinePatchOffsets) {
        $rewriteArgs += "--patch-inline-offset"
        $rewriteArgs += $wrapperInlinePatchOffset
    }
    foreach ($wrapperJumpBypassSpec in $wrapperJumpBypassSpecs) {
        $rewriteArgs += "--patch-jump-bypass"
        $rewriteArgs += $wrapperJumpBypassSpec
    }
    foreach ($resolveRedirectSpec in $resolveRedirectSpecs) {
        $rewriteArgs += "--resolve-redirect"
        $rewriteArgs += $resolveRedirectSpec
    }
    if ($enable947StartupResolveRedirects) {
        $rewriteArgs += "--force-secure-retail-startup-redirects"
    }

    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    Write-LaunchTrace ("wrapper rewrite helper start exe={0}" -f $clientLaunchPath)
    $quotedRewriteArgs = @($rewriteArgs | ForEach-Object { Quote-ProcessArgument $_ })
    $wrapperRewriteHelper = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $quotedRewriteArgs `
        -WorkingDirectory $root `
        -RedirectStandardOutput $wrapperRewriteStdout `
        -RedirectStandardError $wrapperRewriteStderr `
        -PassThru
    Write-LaunchTrace ("wrapper rewrite helper pid={0}" -f $wrapperRewriteHelper.Id)

    $summaryDeadline = (Get-Date).AddSeconds([Math]::Max(15, $StartupTimeoutSeconds))
    while ((Get-Date) -lt $summaryDeadline -and -not (Test-Path $wrapperRewriteSummary)) {
        $helperStillRunning = Get-Process -Id $wrapperRewriteHelper.Id -ErrorAction SilentlyContinue
        if ($null -eq $helperStillRunning) {
            break
        }

        Start-Sleep -Milliseconds 500
    }

    if (-not (Test-Path $wrapperRewriteSummary)) {
        $wrapperHelperExitCode = $null
        try {
            $wrapperRewriteHelper.Refresh()
            if ($wrapperRewriteHelper.HasExited) {
                $wrapperHelperExitCode = $wrapperRewriteHelper.ExitCode
            }
        } catch {}
        Write-LaunchTrace ("wrapper rewrite summary missing helperPid={0} exitCode={1}" -f $wrapperRewriteHelper.Id, $(if ($null -ne $wrapperHelperExitCode) { $wrapperHelperExitCode } else { "running" }))
        if (Test-Path $wrapperRewriteStderr) {
            $stderrTail = (Get-Content -Path $wrapperRewriteStderr -ErrorAction SilentlyContinue | Select-Object -Last 20) -join " | "
            if (-not [string]::IsNullOrWhiteSpace($stderrTail)) {
                Write-LaunchTrace ("wrapper rewrite stderr tail={0}" -f $stderrTail)
            }
        }
        if ((Test-Path $selectedChildExe) -and (Test-Path $directPatchTool)) {
            $fallback = Invoke-WrapperFallbackToDirectPatchedLive `
                -Reason "wrapper-summary-missing" `
                -WrapperExePath $clientLaunchPath `
                -FallbackClientExePath $selectedChildExe `
                -WorkingDirectory $selectedClientDir `
                -LaunchArg $effectiveLaunchArg `
                -SummaryPath $directPatchSummary `
                -TracePath $directPatchTrace `
                -StartupHookOutputPath $directPatchStartupHookOutput `
                -DirectPatchToolPath $directPatchTool `
                -WorkspaceRoot $root `
                -RsaConfigPath $rsaConfigPath `
                -MonitorSeconds $directPatchMonitorSeconds `
                -InlinePatchOffsets $directPatchInlinePatchOffsets `
                -JumpBypassSpecs $directPatchJumpBypassSpecs `
                -RedirectSpecs $resolveRedirectSpecs
            $wrapperFallbackToDirectPatched = $true
            $wrapperFallbackReason = $fallback.Reason
            $directPatchLaunchSummary = $fallback.Launch.Summary
            $resolvedClientPid = $fallback.Launch.ResolvedClientPid
            $client = $fallback.Launch.Client
            $bootstrapClient = $fallback.Launch.BootstrapClient
        } else {
            Stop-WrapperLaunchArtifacts -WrapperExePath $clientLaunchPath | Out-Null
            throw "Wrapper spawn rewrite completed without a summary output: $wrapperRewriteSummary"
        }
    } else {
        Write-LaunchTrace ("wrapper rewrite summary ready helperPid={0}" -f $wrapperRewriteHelper.Id)

        $wrapperSummary = Get-Content -Path $wrapperRewriteSummary -Raw | ConvertFrom-Json
        Write-LaunchTrace ("wrapper rewrite summary loaded wrapperPid={0} childPid={1}" -f $wrapperSummary.wrapperPid, $wrapperSummary.childPid)
        $wrapperFailureReason = $null
        $wrapperDonorCommandLine = if (-not [string]::IsNullOrWhiteSpace([string]$wrapperSummary.rewrittenCommandLine)) {
            [string]$wrapperSummary.rewrittenCommandLine
        } else {
            [string]$wrapperSummary.childCommandLine
        }
        $wrapperFallbackClientArgs = Resolve-WrapperFallbackClientArgs `
            -WrapperChildCommandLine $wrapperDonorCommandLine `
            -LaunchArg $effectiveLaunchArg
        if ($null -eq $wrapperSummary.childPid -or [string]::IsNullOrWhiteSpace([string]$wrapperSummary.childPid)) {
            $wrapperFailureReason = "wrapper-child-pid-missing"
        } elseif (
            $configuredClientBuild -ge 947 -and
            $useRuneScapeWrapper -and
            (Test-Path $selectedChildExe) -and
            -not [string]::IsNullOrWhiteSpace([string]$wrapperSummary.childPath)
        ) {
            $expectedChildPath = [System.IO.Path]::GetFullPath($selectedChildExe)
            $actualChildPath = [System.IO.Path]::GetFullPath([string]$wrapperSummary.childPath)
            if (-not [string]::Equals($expectedChildPath, $actualChildPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                $installedRuntimeChildPath = if (-not [string]::IsNullOrWhiteSpace($installedGameClientExe) -and (Test-Path $installedGameClientExe)) {
                    [System.IO.Path]::GetFullPath($installedGameClientExe)
                } else {
                    $null
                }
                $acceptedChildRefreshReady = $null -ne $installedRuntimeSyncResult -and
                    [bool]$installedRuntimeSyncResult.wrapperLocalChildOverrideReady -and
                    [bool]$installedRuntimeSyncResult.installedReadyAfter
                $wrapperInstalledRuntimeChildReady = $null -ne $installedRuntimeSyncResult -and
                    [bool]$installedRuntimeSyncResult.wrapperInstalledChildReady -and
                    [bool]$installedRuntimeSyncResult.installedReadyAfter
                if (
                    ($acceptedChildRefreshReady -or $wrapperInstalledRuntimeChildReady) -and
                    -not [string]::IsNullOrWhiteSpace($installedRuntimeChildPath) -and
                    [string]::Equals($installedRuntimeChildPath, $actualChildPath, [System.StringComparison]::OrdinalIgnoreCase)
                ) {
                    Write-LaunchTrace ("wrapper child stayed on synced installed runtime path; accepting child path={0}" -f $actualChildPath)
                    $wrapperAcceptedInstalledRuntimeChild = $true
                } else {
                    $wrapperFailureReason = "wrapper-child-override-mismatch"
                }
            }
        }

        if (-not [string]::IsNullOrWhiteSpace($wrapperFailureReason) -and (Test-Path $selectedChildExe) -and (Test-Path $directPatchTool)) {
            $fallback = Invoke-WrapperFallbackToDirectPatchedLive `
                -Reason $wrapperFailureReason `
                -WrapperExePath $clientLaunchPath `
                -FallbackClientExePath $selectedChildExe `
                -WorkingDirectory $selectedClientDir `
                -LaunchArg $effectiveLaunchArg `
                -FallbackClientArgs $wrapperFallbackClientArgs `
                -SummaryPath $directPatchSummary `
                -TracePath $directPatchTrace `
                -StartupHookOutputPath $directPatchStartupHookOutput `
                -DirectPatchToolPath $directPatchTool `
                -WorkspaceRoot $root `
                -RsaConfigPath $rsaConfigPath `
                -MonitorSeconds $directPatchMonitorSeconds `
                -InlinePatchOffsets $directPatchInlinePatchOffsets `
                -JumpBypassSpecs $directPatchJumpBypassSpecs `
                -RedirectSpecs $resolveRedirectSpecs
            $wrapperFallbackToDirectPatched = $true
            $wrapperFallbackReason = $fallback.Reason
            $directPatchLaunchSummary = $fallback.Launch.Summary
            $resolvedClientPid = $fallback.Launch.ResolvedClientPid
            $client = $fallback.Launch.Client
            $bootstrapClient = $fallback.Launch.BootstrapClient
        } else {
            if ($null -eq $wrapperSummary.childPid -or [string]::IsNullOrWhiteSpace([string]$wrapperSummary.childPid)) {
                Stop-WrapperLaunchArtifacts -WrapperExePath $clientLaunchPath | Out-Null
                throw "Wrapper spawn rewrite completed without a child process id: $wrapperRewriteSummary"
            }
            $wrapperPid = [int]$wrapperSummary.wrapperPid
            $resolvedClientPid = [int]$wrapperSummary.childPid
            if ($AutoSwitchGraphicsCompat.IsPresent -and (Test-Path $graphicsDialogHelper)) {
                $helperJson = & $graphicsDialogHelper -Action Switch -TimeoutSeconds ([Math]::Max(15, $StartupTimeoutSeconds)) -SummaryOutput $graphicsDialogSummary
                if (-not [string]::IsNullOrWhiteSpace($helperJson)) {
                    $graphicsHelperResult = $helperJson | ConvertFrom-Json
                }
            }
            Stop-InstalledJagexLauncherProcesses
            Start-Sleep -Seconds ([Math]::Min(15, [Math]::Max(5, [int][Math]::Ceiling($StartupTimeoutSeconds / 6.0))))
            $client = Resolve-WrapperClientProcess -WrapperPid $wrapperPid -ChildPid $resolvedClientPid -TimeoutSeconds 10
            Write-LaunchTrace ("wrapper resolve initial childPid={0} resolvedPid={1}" -f $resolvedClientPid, $(if ($client) { $client.Id } else { 0 }))
            if ($null -eq $client -and $wrapperPid) {
                $client = Get-Process -Id $wrapperPid -ErrorAction SilentlyContinue
                if ($null -ne $client) {
                    Write-LaunchTrace ("wrapper resolve falling back to wrapper pid={0}" -f $wrapperPid)
                }
            }
            if ($null -eq $client -and (Test-Path $selectedChildExe) -and (Test-Path $directPatchTool)) {
                $fallback = Invoke-WrapperFallbackToDirectPatchedLive `
                    -Reason "wrapper-client-process-missing" `
                    -WrapperExePath $clientLaunchPath `
                    -FallbackClientExePath $selectedChildExe `
                    -WorkingDirectory $selectedClientDir `
                    -LaunchArg $effectiveLaunchArg `
                    -SummaryPath $directPatchSummary `
                    -TracePath $directPatchTrace `
                    -StartupHookOutputPath $directPatchStartupHookOutput `
                    -DirectPatchToolPath $directPatchTool `
                    -WorkspaceRoot $root `
                    -RsaConfigPath $rsaConfigPath `
                    -MonitorSeconds $directPatchMonitorSeconds `
                    -InlinePatchOffsets $directPatchInlinePatchOffsets `
                    -JumpBypassSpecs $directPatchJumpBypassSpecs `
                    -RedirectSpecs $resolveRedirectSpecs
                $wrapperFallbackToDirectPatched = $true
                $wrapperFallbackReason = $fallback.Reason
                $directPatchLaunchSummary = $fallback.Launch.Summary
                $resolvedClientPid = $fallback.Launch.ResolvedClientPid
                $client = $fallback.Launch.Client
                $bootstrapClient = $fallback.Launch.BootstrapClient
            } elseif ($null -eq $client) {
                throw "Wrapper launch completed but no live RuneScape client process could be resolved."
            } else {
                $bootstrapClient = [pscustomobject]@{ Id = $wrapperPid }
            }
        }
    }
} else {
    $bootstrapClient = Start-Process @clientStartArgs
    if ($AutoSwitchGraphicsCompat.IsPresent -and $useRuneScapeWrapper -and (Test-Path $graphicsDialogHelper)) {
        $helperJson = & $graphicsDialogHelper -Action Switch -TimeoutSeconds ([Math]::Max(15, $StartupTimeoutSeconds)) -SummaryOutput $graphicsDialogSummary
        if (-not [string]::IsNullOrWhiteSpace($helperJson)) {
            $graphicsHelperResult = $helperJson | ConvertFrom-Json
        }
    }
    if ($useRuneScapeWrapper) {
        Stop-InstalledJagexLauncherProcesses
    }
    $client = Resolve-MainClientProcess -BootstrapPid $bootstrapClient.Id -TimeoutSeconds 10
    if ($null -eq $client) {
        $client = $bootstrapClient
    }
}
Write-LaunchTrace "client bootstrapPid=$($bootstrapClient.Id) pid=$($client.Id)"

$json = [pscustomobject]@{
    WrapperPid = if ($useRuneScapeWrapper -and -not $wrapperFallbackToDirectPatched) { $bootstrapClient.Id } else { $null }
    WrapperHelperPid = if ($wrapperRewriteHelper -and -not $wrapperFallbackToDirectPatched) { $wrapperRewriteHelper.Id } else { $null }
    ServerPid = $serverPid
    ServerLaunchMode = $serverLaunchMode
    LobbyProxyPid = $lobbyProxyPid
    GameProxyPid = $gameProxyPid
    WatchdogPid = if ($watchdog) { $watchdog.Id } else { $null }
    BootstrapClientPid = $bootstrapClient.Id
    ClientPid = $client.Id
    ProxyMode = if ($EnableProxySupport) { "live-capture" } else { "local" }
    ProxyUsernames = $normalizedProxyUsernames
    ServerOut = $serverOut
    ServerErr = $serverErr
    WatchdogOut = $watchdogOut
    WatchdogErr = $watchdogErr
    ClientBuild = $configuredClientBuild
    AutoSelectedOriginalClient = $false
    ClientLaunchBinaryKind = if ($UsePatchedLauncher) {
        "patched-launcher"
    } elseif ($useDirectPatchedRs2Client -or $wrapperFallbackToDirectPatched) {
        "direct-patched-rs2client"
    } elseif ($useRuneScapeWrapper) {
        "runescape-wrapper"
    } else {
        "rs2client"
    }
    ClientExe = $clientLaunchPath
    StagedRuneScapeWrapper = $stagedRuneScapeWrapper
    ClientArgs = $effectiveClientArgs
    DirectPatchSummary = if ($directPatchLaunchSummary) { $directPatchSummary } else { $null }
    DirectPatchStartupHookOutput = if ($directPatchLaunchSummary -and -not [string]::IsNullOrWhiteSpace($directPatchStartupHookOutput)) { $directPatchStartupHookOutput } else { $null }
    DirectPatchInlinePatchOffsets = $directPatchInlinePatchOffsets
    DirectPatchJumpBypassSpecs = $directPatchJumpBypassSpecs
    WrapperExtraArgs = $wrapperExtraArgs
    WrapperInlinePatchOffsets = $wrapperInlinePatchOffsets
    WrapperJumpBypassSpecs = $wrapperJumpBypassSpecs
    Disable947InlineNullReadPatches = [bool]$Disable947InlineNullReadPatches.IsPresent
    Disable947JumpBypassGuards = [bool]$Disable947JumpBypassGuards.IsPresent
    DisableChecksumOverride = $DisableChecksumOverride.IsPresent
    RequestedBypassGameProxy = $BypassGameProxy.IsPresent
    BypassGameProxy = $script:EffectiveBypassGameProxy
    LobbyTlsPassthrough = $script:EffectiveLobbyTlsPassthrough
    ForceLobbyTlsMitm = $ForceLobbyTlsMitm.IsPresent
    DisableLobbyTlsPassthroughAuto = $DisableLobbyTlsPassthroughAuto.IsPresent
    ContentTlsRemoteHost = if ([string]::IsNullOrWhiteSpace($script:EffectiveContentTlsRemoteHost)) { $null } else { $script:EffectiveContentTlsRemoteHost }
    ContentTlsRemotePort = if ($script:EffectiveContentTlsRemotePort -gt 0) { $script:EffectiveContentTlsRemotePort } else { $null }
    ContentTlsConnectHost = if ([string]::IsNullOrWhiteSpace($script:EffectiveContentTlsConnectHost)) { $null } else { $script:EffectiveContentTlsConnectHost }
    ContentTlsConnectPort = if ($script:EffectiveContentTlsConnectPort -gt 0) { $script:EffectiveContentTlsConnectPort } else { $null }
    ContentTlsRemoteRaw = $script:EffectiveContentTlsRemoteRaw
    DisableWatchdog = $DisableWatchdog.IsPresent
    UseContentTlsRoute = $script:UseContentTlsRoute
    ContentRouteMode = $script:ContentRouteMode
    LobbyTlsRoutingMode = $script:LobbyTlsRoutingMode
    HostsFileWriteAccess = $script:CanWriteHostsFile
    ResolveRedirectSpecs = $resolveRedirectSpecs
    TlsTrustHealthy = if ($tlsTrustSetup) { [bool]$tlsTrustSetup.TrustState.TrustHealthy } else { $null }
    TlsTrustRepaired = if ($tlsTrustSetup) { [bool]$tlsTrustSetup.Repaired } else { $null }
    TlsTrustThumbprint = if ($tlsTrustSetup) { $tlsTrustSetup.TrustState.ActiveThumbprint } else { $null }
    TlsTrustSubject = if ($tlsTrustSetup) { $tlsTrustSetup.TrustState.ActiveSubject } else { $null }
    TlsDirectLeafTrusted = if ($tlsTrustSetup) { [bool]$tlsTrustSetup.TrustState.DirectLeafTrusted } else { $null }
    TlsTrustPfxPath = if ($tlsTrustSetup) { $tlsTrustSetup.TrustState.PfxPath } else { $null }
    DownloadMetadataSource = $resolvedDownloadMetadataSource
    ClientStdout = if ($CaptureConsole -and -not $UsePatchedLauncher) { $clientStdout } else { $null }
    ClientStderr = if ($CaptureConsole -and -not $UsePatchedLauncher) { $clientStderr } else { $null }
    ClientCefLog = if ($EnableCefLogging) { $clientCefLog } else { $null }
    GraphicsDialogSummary = if ($graphicsHelperResult) { $graphicsDialogSummary } else { $null }
    GraphicsDialogInvoked = if ($graphicsHelperResult) { [bool]$graphicsHelperResult.Invoked } else { $null }
    GraphicsDeviceSummary = if ($graphicsDeviceResult) { $graphicsDeviceSummary } else { $null }
    LauncherGraphicsDevice = if ($launcherPreferencesResult) { $launcherPreferencesResult.After.GraphicsDevice } else { $null }
    LauncherPreferencesSummary = if ($launcherPreferencesResult) { $launcherPreferencesSummary } else { $null }
    LauncherCompatibilityForced = if ($launcherPreferencesResult) { $launcherPreferencesResult.After.Compatibility } else { $null }
    LauncherPreferencesChangedKeys = if ($launcherPreferencesResult) { @($launcherPreferencesResult.ChangedKeys) } else { @() }
    GpuPreferenceSummary = if ($gpuPreferenceResult) { $gpuPreferenceSummary } else { $null }
    GpuPreferenceChangedPaths = if ($gpuPreferenceResult) { @($gpuPreferenceResult.ChangedPaths) } else { @() }
    GpuPreferenceTargetPaths = if ($gpuPreferenceResult) { @($gpuPreferenceResult.Entries | ForEach-Object { $_.ExecutablePath }) } else { @() }
    RuntimeCacheSyncSummary = if ($runtimeCacheSyncResult) { $runtimeCacheSyncSummary } else { $null }
    RuntimeCacheSyncSkipped = [bool]$runtimeCacheSyncSkippedEffective
    RuntimeCacheSyncAutoSkipped = [bool]$runtimeAutoSkipCacheSync947Retail
    RuntimeCacheSyncPlannedCopyCount = if ($runtimeCacheSyncResult) { [int]$runtimeCacheSyncResult.PlannedCopyCount } else { 0 }
    RuntimeCacheSyncCopiedCount = if ($runtimeCacheSyncResult) { [int]$runtimeCacheSyncResult.CopiedCount } else { 0 }
    RuntimeCacheSyncCopiedArchives = if ($runtimeCacheSyncResult) { @($runtimeCacheSyncResult.CopiedArchives) } else { @() }
    RuntimeCacheSyncCopiedHotArchives = if ($runtimeCacheSyncResult) { @($runtimeCacheSyncResult.CopiedHotArchiveIds) } else { @() }
    RuntimeHotCacheRepairAutoTriggered = [bool](-not $RepairRuntimeHotCache.IsPresent -and -not [string]::IsNullOrWhiteSpace($runtimeAutoRepairReason))
    RuntimeHotCacheRepairReason = if (-not [string]::IsNullOrWhiteSpace($runtimeAutoRepairReason)) { $runtimeAutoRepairReason } elseif ($RepairRuntimeHotCache.IsPresent) { "manual" } else { $null }
    RuntimeHotCacheRepairArchiveIds = @($runtimeHotCacheRepairArchiveIds)
    InstalledRuntimeSyncSummary = if ($installedRuntimeSyncResult) { $installedRuntimeSyncSummary } else { $null }
    InstalledRuntimeSyncLocalDir = if ($installedRuntimeSyncResult) { $runtimeSyncLocalDir } else { $null }
    InstalledRuntimeSyncLocalReady = if ($installedRuntimeSyncResult) { [bool]$installedRuntimeSyncResult.localReady } else { $null }
    InstalledRuntimeSyncInstalledReadyBefore = if ($installedRuntimeSyncResult) { [bool]$installedRuntimeSyncResult.installedReadyBefore } else { $null }
    InstalledRuntimeSyncInstalledReadyAfter = if ($installedRuntimeSyncResult) { [bool]$installedRuntimeSyncResult.installedReadyAfter } else { $null }
    InstalledRuntimeSyncPlannedCopyCount = if ($installedRuntimeSyncResult) { [int]$installedRuntimeSyncResult.plannedCopyCount } else { 0 }
    InstalledRuntimeSyncCopiedCount = if ($installedRuntimeSyncResult) { [int]$installedRuntimeSyncResult.copiedCount } else { 0 }
    InstalledRuntimeSyncCopiedFiles = if ($installedRuntimeSyncResult) { @($installedRuntimeSyncResult.copiedFiles) } else { @() }
    InstalledRuntimeSyncFailedFiles = if ($installedRuntimeSyncResult) { @($installedRuntimeSyncResult.failedFiles) } else { @() }
    WrapperAcceptedInstalledRuntimeChild = $wrapperAcceptedInstalledRuntimeChild
    WrapperFallbackToDirectPatched = $wrapperFallbackToDirectPatched
    WrapperFallbackReason = $wrapperFallbackReason
    LaunchStateFile = $launchStateFile
    LaunchMode = if ($UsePatchedLauncher) {
        "patched-launcher"
    } elseif ($useDirectPatchedRs2Client -or $wrapperFallbackToDirectPatched) {
        "direct-patched-client"
    } elseif ($useRuneScapeWrapper) {
        "runescape-wrapper"
    } elseif ($effectiveUseOriginalClient) {
        "direct-original-client"
    } else {
        "direct-client"
    }
} | ConvertTo-Json -Depth 3
Write-LaunchTrace ("writing launch state file={0}" -f $launchStateFile)
Set-Content -Path $launchStateFile -Value $json -Encoding ASCII
Write-LaunchTrace ("launch state written file={0}" -f $launchStateFile)
Write-Output $json
Write-LaunchTrace "launch-win64c-live completed"

exit 0
