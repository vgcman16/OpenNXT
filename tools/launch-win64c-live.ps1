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
    [switch]$AutoSwitchGraphicsCompat,
    [switch]$UseRuneScapeWrapper
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
$launchArg = "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0"
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
$windowsGpuPreferenceScript = Join-Path $PSScriptRoot "set_windows_gpu_preference.ps1"
$runtimeCacheSyncScript = Join-Path $PSScriptRoot "sync_runescape_runtime_cache.ps1"
$runtimeHotCacheRepairScript = Join-Path $PSScriptRoot "repair_runescape_runtime_hot_cache.ps1"
$installedRuntimeSyncTool = Join-Path $PSScriptRoot "sync_runescape_installed_runtime.py"
$directPatchTrace = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-live.jsonl"
$directPatchSummary = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-live.json"
$directPatchStartupHookOutput = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-live-hook.jsonl"
$wrapperRewriteTrace = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live.jsonl"
$wrapperRewriteSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live.json"
$wrapperRewriteChildHookOutput = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-child-hook.jsonl"
$wrapperRewriteStdout = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live.stdout.log"
$wrapperRewriteStderr = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live.stderr.log"
$graphicsDialogSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-graphics-dialog.json"
$launcherPreferencesSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-launcher-preferences.json"
$gpuPreferenceSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-gpu-preference.json"
$runtimeCacheSyncSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-runtime-cache-sync.json"
$runtimeHotCacheRepairSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-runtime-hot-cache-repair.json"
$installedRuntimeSyncSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-installed-runtime-sync.json"
$installedRuntimePostLaunchVerifySummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-live-installed-runtime-post-launch-check.json"
$rsaConfigPath = Join-Path $root "data\\config\\rsa.toml"
$launchTrace = Join-Path $root "tmp-launch-win64c-live.trace.log"
$launchStateFile = Join-Path $root "tmp-launch-win64c-live.state.json"
$startupConfigSnapshotPath = Join-Path $root "tmp-947-startup-config.ws"
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
        [string[]]$RedirectSpecs = @()
    )

    if (Test-Path $SummaryPath) {
        Remove-Item $SummaryPath -Force -ErrorAction SilentlyContinue
    }
    if (-not [string]::IsNullOrWhiteSpace($StartupHookOutputPath) -and (Test-Path $StartupHookOutputPath)) {
        Remove-Item $StartupHookOutputPath -Force -ErrorAction SilentlyContinue
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
    foreach ($redirectSpec in $RedirectSpecs) {
        $directPatchArgs += "--resolve-redirect"
        $directPatchArgs += $redirectSpec
    }

    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    Push-Location $WorkspaceRoot
    try {
        & $pythonExe @directPatchArgs
        $directPatchExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($directPatchExitCode -ne 0) {
        throw "Direct rs2client patch launch failed with exit code $directPatchExitCode."
    }
    if (-not (Test-Path $SummaryPath)) {
        throw "Direct rs2client patch launch completed without a summary output: $SummaryPath"
    }

    $directPatchLaunchSummary = Get-Content -Path $SummaryPath -Raw | ConvertFrom-Json
    $resolvedClientPid = [int]$directPatchLaunchSummary.pid
    $client = Get-Process -Id $resolvedClientPid -ErrorAction SilentlyContinue
    if ($null -eq $client -and [bool]$directPatchLaunchSummary.processAlive) {
        $client = Resolve-MainClientProcess -BootstrapPid $resolvedClientPid -TimeoutSeconds 10
    }
    if ($null -eq $client) {
        throw "Direct rs2client patch launch completed but no live client process could be resolved."
    }

    return [pscustomobject]@{
        Summary = $directPatchLaunchSummary
        BootstrapClient = [pscustomobject]@{ Id = $resolvedClientPid }
        Client = $client
        ResolvedClientPid = $resolvedClientPid
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
    foreach ($extraTlsMitmHost in $extraTlsMitmHosts) {
        $lobbyProxyArgs += @(
            "-TlsExtraMitmHost",
            $extraTlsMitmHost
        )
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

    $hostsScript = if ($script:UseContentTlsRoute) { $setContentHostsOverrideScript } else { $clearContentHostsOverrideScript }
    $action = if ($script:UseContentTlsRoute) { "apply" } else { "clear" }

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
            # client in the local raw 255/* refresh loop before login.
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "gamePortOverride"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "0"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "liveCache"
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
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource"
            $effectiveLaunchArg = Remove-QueryParameter -Url $effectiveLaunchArg -Name "liveCache"
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
    if (-not $prefer947PatchedDirectClient) {
        # Keep the canonical MITM launch shape explicit for the wrapper/retail route.
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "hostRewrite" -Value "0"
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "lobbyHostRewrite" -Value "0"
        if ($configuredClientBuild -ge 947) {
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "0"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "codebaseRewrite" -Value "1"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "gameHostRewrite" -Value "0"
        } else {
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "1"
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "gameHostOverride" -Value $canonicalLoopbackGameHost
            $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "gamePortOverride" -Value $configuredGamePort
        }
    }
} else {
    $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "contentRouteRewrite" -Value "0"
}
if ($useRuneScapeWrapperPreview) {
    if ($configuredClientBuild -lt 947) {
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "worldUrlRewrite" -Value "1"
        $effectiveLaunchArg = Set-QueryParameter -Url $effectiveLaunchArg -Name "baseConfigSource" -Value "compressed"
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

$runtimeCopiedHotArchiveIds = @()
$runtimeAutoRepairReason = $null
$runtimeShouldAutoRepairHotCache947 = $false
$runtimeHotCacheRepairArchiveIds = @()
$runtimeHotStubArchiveIds = @()
$runtimeShouldPreserveHotArchiveSet = $false

if ($configuredClientBuild -ge 947 -and -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and (Test-Path $runtimeCacheSyncScript)) {
    $runtimeCacheSourceDir = Join-Path $root "data\\cache"
    $runtimeCacheTargetDir = Join-Path $env:ProgramData "Jagex\\RuneScape"
    Write-LaunchTrace ("runtime cache sync start source={0} runtime={1}" -f $runtimeCacheSourceDir, $runtimeCacheTargetDir)
    $runtimeSourceFiles = @(
        Get-ChildItem -Path $runtimeCacheSourceDir -Filter "js5-*.jcache" -File -ErrorAction SilentlyContinue
    )
    $runtimeTargetFiles = @(
        Get-ChildItem -Path $runtimeCacheTargetDir -Filter "js5-*.jcache" -File -ErrorAction SilentlyContinue
    )
    $runtimeHotStubArchiveIds = @(
        foreach ($archiveId in $runtimeHotArchiveIds947) {
            $runtimeArchivePath = Join-Path $runtimeCacheTargetDir ("js5-{0}.jcache" -f $archiveId)
            if (Test-Path $runtimeArchivePath) {
                $runtimeArchive = Get-Item -LiteralPath $runtimeArchivePath -ErrorAction SilentlyContinue
                if ($runtimeArchive -and $runtimeArchive.Length -le 12288) {
                    $archiveId
                }
            }
        }
    )
    $runtimeMissingHotArchiveIds = @(
        foreach ($archiveId in $runtimeHotArchiveIds947) {
            $runtimeArchivePath = Join-Path $runtimeCacheTargetDir ("js5-{0}.jcache" -f $archiveId)
            if (-not (Test-Path $runtimeArchivePath)) {
                $archiveId
            }
        }
    )
    $runtimeUsesRetailStartupConfig = $configuredClientBuild -ge 947 -and $use947RetailConfigHost
    $runtimePromoteToFullSync = $runtimeUsesRetailStartupConfig -or ($prefer947PatchedDirectClient -and ($runtimeTargetFiles.Count -lt $runtimeSourceFiles.Count -or $runtimeHotStubArchiveIds.Count -gt 0))
    $runtimeSyncMode = if ($runtimePromoteToFullSync) { "full" } else { "seed-missing" }
    $runtimeClientManagedHotArchiveSet = $configuredClientBuild -ge 947 -and $runtimeUsesRetailStartupConfig -and $prefer947PatchedDirectClient -and $runtimeMissingHotArchiveIds.Count -eq 0
    Write-LaunchTrace ("runtime cache sync mode={0} sourceCount={1} runtimeCount={2} hotStubCount={3} hotStubArchives={4}" -f $runtimeSyncMode, $runtimeSourceFiles.Count, $runtimeTargetFiles.Count, $runtimeHotStubArchiveIds.Count, (($runtimeHotStubArchiveIds | ForEach-Object { [string]$_ }) -join ","))
    $runtimeCacheSyncParameters = @{
        SourceCacheDir = $runtimeCacheSourceDir
        RuntimeCacheDir = $runtimeCacheTargetDir
        SummaryOutput  = $runtimeCacheSyncSummary
        NoOutput       = $true
    }
    $runtimeShouldPreserveHotArchiveSet = $runtimeClientManagedHotArchiveSet -or ((-not $prefer947PatchedDirectClient) -and (-not $runtimeUsesRetailStartupConfig) -and -not $RepairRuntimeHotCache.IsPresent)
    # Once the direct 947 retail-shaped path has a complete hot splash set, let
    # the client own those ProgramData archives. They are valid even when their
    # SQLite cache_index rows are empty, and force-repairing them every launch
    # just sends splash back into another warmup cycle.
    if ($runtimeShouldPreserveHotArchiveSet) {
        $runtimeCacheSyncParameters["SkipJs5Archives"] = $runtimeHotArchiveIds947
        if (-not $runtimeClientManagedHotArchiveSet) {
            $runtimeCacheSyncParameters["ValidateSkippedArchives"] = $true
        }
    }
    if ($runtimeShouldPreserveHotArchiveSet -and -not $runtimeClientManagedHotArchiveSet -and $runtimeHotStubArchiveIds.Count -gt 0) {
        $runtimeCacheSyncParameters["RescueSkippedBootstrapStubs"] = $true
    }
    if (-not $runtimePromoteToFullSync) {
        $runtimeCacheSyncParameters["SeedMissingOnly"] = $true
    }
    & $runtimeCacheSyncScript @runtimeCacheSyncParameters
    if (Test-Path $runtimeCacheSyncSummary) {
        $runtimeCacheSyncResult = Get-Content -Path $runtimeCacheSyncSummary -Raw | ConvertFrom-Json
        $runtimeCacheSyncResult | Add-Member -NotePropertyName SyncMode -NotePropertyValue $runtimeSyncMode -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName RuntimeSourceCount -NotePropertyValue $runtimeSourceFiles.Count -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName RuntimeTargetCountBefore -NotePropertyValue $runtimeTargetFiles.Count -Force
        $runtimeCacheSyncResult | Add-Member -NotePropertyName HotStubArchiveIdsBefore -NotePropertyValue @($runtimeHotStubArchiveIds) -Force
        $runtimeCopiedHotArchiveIds = @(
            @($runtimeCacheSyncResult.CopiedArchives) |
                Where-Object { $runtimeHotArchiveIds947 -contains [int]$_ } |
                ForEach-Object { [int]$_ } |
                Select-Object -Unique
        )
        $runtimeCacheSyncResult | Add-Member -NotePropertyName CopiedHotArchiveIds -NotePropertyValue @($runtimeCopiedHotArchiveIds) -Force
        Write-LaunchTrace ("runtime cache sync mode={0} rescued={1} copied={2} unchanged={3} skipped={4} skipArchives={5}" -f $runtimeSyncMode, $runtimeCacheSyncResult.RescuedCount, $runtimeCacheSyncResult.CopiedCount, $runtimeCacheSyncResult.UnchangedCount, $runtimeCacheSyncResult.SkippedCount, (($runtimeCacheSyncResult.SkipJs5Archives | ForEach-Object { [string]$_ }) -join ","))
    } else {
        Write-LaunchTrace "runtime cache sync summary missing"
    }
}

$runtimeShouldAutoRepairHotCache947 = $configuredClientBuild -ge 947 -and $runtimeShouldPreserveHotArchiveSet -and -not $runtimeClientManagedHotArchiveSet -and $runtimeHotStubArchiveIds.Count -gt 0
if ($runtimeShouldAutoRepairHotCache947 -and -not $RepairRuntimeHotCache.IsPresent) {
    $runtimeAutoRepairReason = "auto-hot-stub-quarantine"
}
$runtimeHotCacheRepairArchiveIds = if ($RepairRuntimeHotCache.IsPresent) {
    @($runtimeHotArchiveIds947)
} elseif ($runtimeShouldAutoRepairHotCache947) {
    @($runtimeHotStubArchiveIds)
} else {
    @()
}
Write-LaunchTrace ("runtime hot cache repair decision mode={0} archiveCount={1} archives={2}" -f $(if ($RepairRuntimeHotCache.IsPresent) { "manual" } elseif (-not [string]::IsNullOrWhiteSpace($runtimeAutoRepairReason)) { $runtimeAutoRepairReason } else { "skip" }), $runtimeHotCacheRepairArchiveIds.Count, (($runtimeHotCacheRepairArchiveIds | ForEach-Object { [string]$_ }) -join ","))

if (
    ($RepairRuntimeHotCache.IsPresent -or $runtimeShouldAutoRepairHotCache947) -and
    -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and
    (Test-Path $runtimeHotCacheRepairScript) -and
    $runtimeHotCacheRepairArchiveIds.Count -gt 0
) {
    Write-LaunchTrace ("runtime hot cache repair start runtime={0}" -f (Join-Path $env:ProgramData "Jagex\\RuneScape"))
    & $runtimeHotCacheRepairScript `
        -RuntimeCacheDir (Join-Path $env:ProgramData "Jagex\\RuneScape") `
        -ArchiveIds $runtimeHotCacheRepairArchiveIds `
        -IncludeAuxiliaryFiles `
        -SummaryOutput $runtimeHotCacheRepairSummary `
        -NoOutput
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
    if (-not (Wait-ListeningPorts -Ports $serverPorts -TimeoutSeconds $StartupTimeoutSeconds)) {
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
            if (-not (Wait-ListeningPorts -Ports $serverPorts -TimeoutSeconds $fallbackTimeoutSeconds)) {
                throw "Timed out waiting for OpenNXT server ports $configuredHttpPort and $configuredGameBackendPort after fallback startup"
            }
        } else {
            throw "Timed out waiting for OpenNXT server ports $configuredHttpPort and $configuredGameBackendPort after $StartupTimeoutSeconds seconds"
        }
    }
    Write-LaunchTrace "server ports ready"

    $serverPid = Get-ListeningProcessIds -Ports $serverPorts | Select-Object -First 1
    Write-LaunchTrace "server pid=$serverPid mode=$serverLaunchMode"

    if ($configuredClientBuild -ge 947 -and $use947RetailConfigHost -and -not $prefer947PatchedDirectClient -and $script:UseContentTlsRoute -and -not $script:CanWriteHostsFile) {
        $startupConfigContent = Get-947StartupConfigContent -ConfigUrl $effectiveLaunchArg -HttpPort $configuredHttpPort
        if (-not [string]::IsNullOrWhiteSpace($startupConfigContent)) {
            $startupRouteHosts = @(Get-947StartupRouteHostsFromConfigContent -ConfigContent $startupConfigContent)
            $startupRedirectHosts = @(
                @(Get-947StartupWorldMitmHostsFromConfigContent -ConfigContent $startupConfigContent) |
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
            Write-LaunchTrace "947 startup secure resolve redirects=<config-fetch-failed>"
        }
    }

    if ($configuredClientBuild -ge 947 -and -not $use947RetailConfigHost) {
        $startupConfigContent = Get-947StartupConfigContent -ConfigUrl $effectiveLaunchArg -HttpPort $configuredHttpPort
        if (-not [string]::IsNullOrWhiteSpace($startupConfigContent)) {
            if (Save-947StartupConfigSnapshot -ConfigContent $startupConfigContent -OutputPath $startupConfigSnapshotPath) {
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
        Write-LaunchTrace ("installed runtime sync localReady={0} installedReadyAfter={1} copied={2} failed={3}" -f $installedRuntimeSyncResult.localReady, $installedRuntimeSyncResult.installedReadyAfter, $installedRuntimeSyncResult.copiedCount, $installedRuntimeSyncResult.failedCount)
    } else {
        Write-LaunchTrace "installed runtime sync summary missing"
    }
    if ($null -ne $installedRuntimeSyncResult -and -not [bool]$installedRuntimeSyncResult.localReady) {
        throw "Installed runtime sync refused to continue because the staged local 947 client family does not match the live manifest."
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
$gpuPreferenceResult = $null
if ($autoManageGraphicsCompat -and ($useRuneScapeWrapper -or $useDirectPatchedRs2Client) -and (Test-Path $launcherPreferencesScript)) {
    $launcherPreferenceParams = @{
        Compatibility = "true"
        ClearDontAskAgain = $true
        SummaryOutput = $launcherPreferencesSummary
    }
    if ($configuredClientBuild -ge 947) {
        $launcherPreferenceParams.GraphicsDevice = "default"
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
        $gpuPreferenceJson = & $windowsGpuPreferenceScript -ExecutablePath $gpuTargets -Preference "high-performance" -SummaryOutput $gpuPreferenceSummary
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
        $wrapperExtraArgs += "--useAngle"
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
        $wrapperInlinePatchOffsets += "0x594a41"
        $wrapperInlinePatchOffsets += "0x594d61"
        $wrapperJumpBypassSpecs += "0x59002d:0x5900a5"
        $wrapperJumpBypassSpecs += "0x59034d:0x5903c5"
        $wrapperJumpBypassSpecs += "0x590c72:0x590dcb"
        $wrapperJumpBypassSpecs += "0x590f92:0x5910eb"
        $wrapperJumpBypassSpecs += "0x594a88:0x594aa1"
        $wrapperJumpBypassSpecs += "0x594a91:0x594aa1"
        $wrapperJumpBypassSpecs += "0x594aa6:0x594aba"
        $wrapperJumpBypassSpecs += "0x594aaf:0x594aba"
        $wrapperJumpBypassSpecs += "0x594da8:0x594dc1"
        $wrapperJumpBypassSpecs += "0x594dc6:0x594dda"
        $wrapperJumpBypassSpecs += "0x72ad28:0x72ad46"
        $wrapperJumpBypassSpecs += "0x72b3a8:0x72b3c6"
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
    $directPatchInlinePatchOffsets += "0x590001"
    $directPatchInlinePatchOffsets += "0x5916c3"
    $directPatchInlinePatchOffsets += "0x5916f0"
    $directPatchInlinePatchOffsets += "0x591712"
    $directPatchInlinePatchOffsets += "0x591719"
    $directPatchJumpBypassSpecs += "0x59002d:0x5900a5"
    $directPatchJumpBypassSpecs += "0x590c72:0x590dcb"
    if ($use947RetailConfigHost) {
        # The secure retail-config direct route still needs the full 0x594a**
        # null-dereference guard cluster to survive startup. The donor/wrapper
        # fallback path also needs the early 0x72ad28 startup guard, but we
        # continue to avoid the later localhost-only compat bypasses.
        $directPatchInlinePatchOffsets += "0x594a41"
        $directPatchJumpBypassSpecs += "0x594a88:0x594aa1"
        $directPatchJumpBypassSpecs += "0x594a91:0x594aa1"
        $directPatchJumpBypassSpecs += "0x594aa6:0x594aba"
        $directPatchJumpBypassSpecs += "0x594aaf:0x594aba"
        $directPatchJumpBypassSpecs += "0x72ad28:0x72ad46"
    } else {
        # The localhost/bootstrap route still needs the broader compat block,
        # but the secure retail-config route stays on the narrower crash
        # guards so we do not short-circuit the 947 splash bootstrap.
        $directPatchInlinePatchOffsets += "0x594a41"
        $directPatchJumpBypassSpecs += "0x594a88:0x594aa1"
        $directPatchJumpBypassSpecs += "0x594a91:0x594aa1"
        $directPatchJumpBypassSpecs += "0x594aa6:0x594aba"
        $directPatchJumpBypassSpecs += "0x594aaf:0x594aba"
        $directPatchJumpBypassSpecs += "0x72ad28:0x72ad46"
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
        -MonitorSeconds $StartupTimeoutSeconds `
        -InlinePatchOffsets $directPatchInlinePatchOffsets `
        -JumpBypassSpecs $directPatchJumpBypassSpecs `
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
        $rewriteArgs += "20"
        if (Test-Path $selectedChildExe) {
            $rewriteArgs += "--child-exe-override"
            $rewriteArgs += $selectedChildExe
        }
    }
    if (Test-Path $rsaConfigPath) {
        $rewriteArgs += "--rsa-config"
        $rewriteArgs += $rsaConfigPath
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
                -MonitorSeconds $StartupTimeoutSeconds `
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
                $installedRuntimeReady = $null -ne $installedRuntimeSyncResult -and
                    [bool]$installedRuntimeSyncResult.localReady -and
                    [bool]$installedRuntimeSyncResult.installedReadyAfter
                if (
                    $installedRuntimeReady -and
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
                -MonitorSeconds $StartupTimeoutSeconds `
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
                    -MonitorSeconds $StartupTimeoutSeconds `
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
    LauncherPreferencesSummary = if ($launcherPreferencesResult) { $launcherPreferencesSummary } else { $null }
    LauncherCompatibilityForced = if ($launcherPreferencesResult) { $launcherPreferencesResult.After.Compatibility } else { $null }
    LauncherPreferencesChangedKeys = if ($launcherPreferencesResult) { @($launcherPreferencesResult.ChangedKeys) } else { @() }
    GpuPreferenceSummary = if ($gpuPreferenceResult) { $gpuPreferenceSummary } else { $null }
    GpuPreferenceChangedPaths = if ($gpuPreferenceResult) { @($gpuPreferenceResult.ChangedPaths) } else { @() }
    GpuPreferenceTargetPaths = if ($gpuPreferenceResult) { @($gpuPreferenceResult.Entries | ForEach-Object { $_.ExecutablePath }) } else { @() }
    RuntimeCacheSyncSummary = if ($runtimeCacheSyncResult) { $runtimeCacheSyncSummary } else { $null }
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
Set-Content -Path $launchStateFile -Value $json -Encoding ASCII
Write-Output $json
Write-LaunchTrace "launch-win64c-live completed"

exit 0
