param(
    [string]$ConfigUrl = "",
    [int]$StartupDelaySeconds = 15,
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging,
    [switch]$CaptureConsole,
    [switch]$VerboseStartupHook,
    [switch]$UsePatchedLauncher,
    [string]$ClientExeOverride = "",
    [string]$ClientWorkingDirOverride = "",
    [switch]$AllowExternalClientExe,
    [switch]$UseConfigUriArg,
    [string[]]$ExtraClientArgs = @(),
    [string]$ClientVariant = "patched",
    [switch]$ResetJagexCache,
    [switch]$RepairRuntimeHotCache,
    [switch]$SkipRuntimeCacheSync,
    [string]$DownloadMetadataSource = "patched",
    [switch]$AutoSwitchGraphicsCompat,
    [ValidateSet("auto", "true", "false", "default")]
    [string]$GraphicsCompatibilityMode = "auto",
    [ValidateSet("auto", "default", "power-saving", "high-performance")]
    [string]$GraphicsDevicePreference = "auto",
    [switch]$DisableUseAngle,
    [switch]$UseRuneScapeWrapper,
    [switch]$Force947StartupRouteRedirects,
    [switch]$Enable947LoadingStateBuilderTrace,
    [switch]$Force947LoadingStateRebuild,
    [switch]$Force947RecordStateFromType0,
    [switch]$Disable947InlineNullReadPatches,
    [switch]$Disable947JumpBypassGuards,
    [switch]$AllowRetailJs5Upstream,
    [switch]$DisableWatchdog
)

$ErrorActionPreference = "Stop"
$configUrlExplicit = $PSBoundParameters.ContainsKey("ConfigUrl") -and -not [string]::IsNullOrWhiteSpace($ConfigUrl)

$root = Split-Path -Parent $PSScriptRoot
$powershellExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$stdoutLog = Join-Path $root "tmp-rs2client.stdout.log"
$stderrLog = Join-Path $root "tmp-rs2client.stderr.log"
$cefLogFile = Join-Path $root "tmp-rs2client-cef.log"
$directPatchTool = Join-Path $PSScriptRoot "launch_rs2client_direct_patch.py"
$wrapperRewriteTool = Join-Path $PSScriptRoot "launch_runescape_wrapper_rewrite.py"
$lobbyProxyScript = Join-Path $PSScriptRoot "launch_lobby_tls_terminator.ps1"
$gameProxyScript = Join-Path $PSScriptRoot "launch_game_tls_terminator.ps1"
$tlsTerminateProxyScript = Join-Path $PSScriptRoot "tls_terminate_proxy.py"
$watchdogScript = Join-Path $PSScriptRoot "keep_local_live_stack.ps1"
$contentBootstrapProxyScript = Join-Path $PSScriptRoot "tcp_proxy.py"
$graphicsDialogHelper = Join-Path $PSScriptRoot "invoke_runescape_graphics_dialog_action.ps1"
$launcherPreferencesScript = Join-Path $PSScriptRoot "set_runescape_launcher_preferences.ps1"
$graphicsDeviceResolverScript = Join-Path $PSScriptRoot "resolve_runescape_graphics_device.ps1"
$windowsGpuPreferenceScript = Join-Path $PSScriptRoot "set_windows_gpu_preference.ps1"
$runtimeCacheSyncScript = Join-Path $PSScriptRoot "sync_runescape_runtime_cache.ps1"
$runtimeHotCacheRepairScript = Join-Path $PSScriptRoot "repair_runescape_runtime_hot_cache.ps1"
$installedRuntimeSyncTool = Join-Path $PSScriptRoot "sync_runescape_installed_runtime.py"
$directPatchTrace = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-client-only.jsonl"
$directPatchSummary = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-client-only.json"
$directPatchStdout = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-client-only.stdout.log"
$directPatchStderr = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-client-only.stderr.log"
$wrapperRewriteTrace = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-client-only.jsonl"
$wrapperRewriteSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-client-only.json"
$wrapperRewriteChildHookOutput = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-client-only-child-hook.jsonl"
$graphicsDialogSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-graphics-dialog.json"
$launcherPreferencesSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-launcher-preferences.json"
$graphicsDeviceSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-graphics-device.json"
$gpuPreferenceSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-gpu-preference.json"
$runtimeCacheSyncSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-runtime-cache-sync.json"
$runtimeHotCacheRepairSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-runtime-hot-cache-repair.json"
$installedRuntimeSyncSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-installed-runtime-sync.json"
$installedRuntimePostLaunchVerifySummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-installed-runtime-post-launch-check.json"
$directPatchResourceGateOutputRoot = Join-Path $root "data\\debug\\application-resource-gate-947-direct-helper-client-only"
$directPatchProducerOutputRoot = Join-Path $root "data\\debug\\prelogin-producer-947-direct-helper-client-only"
$directPatchLoadingStateOutputRoot = Join-Path $root "data\\debug\\loading-state-builder-947-direct-helper-client-only"
$startupConfigSnapshotPath = Join-Path $root "tmp-947-startup-config-client-only.ws"
$startupConfigSnapshotReady = $false
$directPatchStartupHookOutput = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-client-only-hook.jsonl"
$lobbyProxyOut = Join-Path $root "tmp-lobby-tls-terminator.out.log"
$lobbyProxyErr = Join-Path $root "tmp-lobby-tls-terminator.err.log"
$contentBootstrapProxyOut = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\content-80-proxy.stdout.log"
$contentBootstrapProxyErr = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\content-80-proxy.stderr.log"
$watchdogOut = Join-Path $root "tmp-client-only-watchdog.out.log"
$watchdogErr = Join-Path $root "tmp-client-only-watchdog.err.log"
$clientOnlyTraceLog = Join-Path $root "tmp-launch-client-only.trace.log"
$serverLauncherScript = Join-Path $PSScriptRoot "start_server_logged.ps1"
$serverConfigPath = Join-Path $root "data\\config\\server.toml"
$certScript = Join-Path $PSScriptRoot "setup_lobby_tls_cert.ps1"
$setContentHostsOverrideScript = Join-Path $PSScriptRoot "set_content_hosts_override.ps1"
$clearContentHostsOverrideScript = Join-Path $PSScriptRoot "clear_content_hosts_override.ps1"
$hostsFile = Join-Path $env:WINDIR "System32\\drivers\\etc\\hosts"
$defaultMitmPrimaryHost = "localhost"
$launcherDir = Join-Path $root "data\\launchers\\win"
$launcherExe = Join-Path $launcherDir "patched.exe"
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

Remove-Item $clientOnlyTraceLog -Force -ErrorAction SilentlyContinue
Remove-Item $startupConfigSnapshotPath -Force -ErrorAction SilentlyContinue

function Write-ClientOnlyTrace {
    param([string]$Message)

    $timestamp = Get-Date -Format "HH:mm:ss.fff"
    Add-Content -Path $clientOnlyTraceLog -Value ("{0} {1}" -f $timestamp, $Message)
}

Write-ClientOnlyTrace "launch-client-only start"

function Get-TomlScalarValue {
    param(
        [string]$Path,
        [string]$Key
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    $line = Select-String -Path $Path -Pattern ("^\s*{0}\s*=\s*(.+?)\s*$" -f [regex]::Escape($Key)) |
        Select-Object -First 1
    if (-not $line) {
        return $null
    }

    $value = $line.Matches[0].Groups[1].Value.Trim()
    if ($value.StartsWith('"') -and $value.EndsWith('"') -and $value.Length -ge 2) {
        return $value.Substring(1, $value.Length - 2)
    }

    return $value
}

function Get-TomlIntValue {
    param(
        [string]$Path,
        [string]$Key,
        [int]$DefaultValue = 947
    )

    $value = Get-TomlScalarValue -Path $Path -Key $Key
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $DefaultValue
    }

    $parsedValue = 0
    if ([int]::TryParse($value, [ref]$parsedValue)) {
        return $parsedValue
    }

    return $DefaultValue
}

function Get-TomlTableScalarValue {
    param(
        [string]$Path,
        [string]$TableName,
        [string]$Key
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    $inTable = $false
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match '^\s*\[(.+?)\]\s*$') {
            $inTable = ($Matches[1] -eq $TableName)
            continue
        }

        if (-not $inTable) {
            continue
        }

        if ($line -match ("^\s*{0}\s*=\s*(.+?)\s*$" -f [regex]::Escape($Key))) {
            $value = $Matches[1].Trim()
            if ($value.StartsWith('"') -and $value.EndsWith('"') -and $value.Length -ge 2) {
                return $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }

    return $null
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

    # The client-only route also rewrites the client-facing content host to
    # localhost, so keep the primary MITM certificate identity pinned to the
    # loopback host and rely on SAN entries for upstream compatibility.
    return $defaultMitmPrimaryHost
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

function Quote-CmdArgument {
    param([string]$Value)

    return Quote-ProcessArgument -Value $Value
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
        $repair = Start-CanonicalMitmTrustRepair -LobbyHost $LobbyHost
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

    return [pscustomobject]@{
        TrustState = $trustState
        Repaired = $repaired
    }
}

function Normalize-LoopbackHost {
    param([string]$HostName)

    if ([string]::IsNullOrWhiteSpace($HostName) -or $HostName -in @("127.0.0.1", "::1", "localhost")) {
        return "localhost"
    }

    return $HostName
}

function Test-PathWithinRoot {
    param(
        [string]$CandidatePath,
        [string]$WorkspaceRoot
    )

    if ([string]::IsNullOrWhiteSpace($CandidatePath) -or [string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
        return $false
    }

    try {
        $fullCandidate = [System.IO.Path]::GetFullPath($CandidatePath)
        $fullRoot = [System.IO.Path]::GetFullPath($WorkspaceRoot)
        if (-not $fullRoot.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
            $fullRoot += [System.IO.Path]::DirectorySeparatorChar
        }
        return $fullCandidate.StartsWith($fullRoot, [System.StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
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

function Sync-RetailHostsOverride {
    param([bool]$EnableOverride)

    if (-not $script:CanWriteHostsFile) {
        return
    }

    $hostsScript = if ($EnableOverride) { $setContentHostsOverrideScript } else { $clearContentHostsOverrideScript }
    if (-not (Test-Path $hostsScript)) {
        throw "Hosts override helper not found: $hostsScript"
    }

    & $powershellExe -ExecutionPolicy Bypass -File $hostsScript | Out-Null
    $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
    if ($exitCode -ne 0) {
        throw "Retail hosts override helper exited with code $exitCode."
    }
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
        [int]$TimeoutSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds([Math]::Max(0, $TimeoutSeconds))
    do {
        $directClient = Get-Process -Name rs2client -ErrorAction SilentlyContinue |
            Sort-Object StartTime -Descending |
            Select-Object -First 1
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

$configuredClientBuild = Get-TomlIntValue -Path $serverConfigPath -Key "build" -DefaultValue 947
$clientVariantExplicit = $PSBoundParameters.ContainsKey("ClientVariant") -and -not [string]::IsNullOrWhiteSpace($ClientVariant)
$effectiveClientVariant = $ClientVariant
$explicitWrapperOverride = $UseRuneScapeWrapper.IsPresent
$originalClientExe = Join-Path $root ("data\\clients\\{0}\\win64c\\original\\rs2client.exe" -f $configuredClientBuild)
$clientDir = Join-Path $root ("data\\clients\\{0}\\win64c\\{1}" -f $configuredClientBuild, $effectiveClientVariant)
$clientExe = Join-Path $clientDir "rs2client.exe"
$explicitClientExeOverride = -not [string]::IsNullOrWhiteSpace($ClientExeOverride)
$prefer947OriginalClientFamily = (
    $configuredClientBuild -ge 947 -and
    $clientVariantExplicit -and
    [string]::Equals($effectiveClientVariant, "original", [System.StringComparison]::OrdinalIgnoreCase)
)
if ($prefer947OriginalClientFamily) {
    $effectiveClientVariant = "original"
    $clientDir = Join-Path $root ("data\\clients\\{0}\\win64c\\{1}" -f $configuredClientBuild, $effectiveClientVariant)
    $clientExe = Join-Path $clientDir "rs2client.exe"
}
if (-not [string]::IsNullOrWhiteSpace($ClientExeOverride)) {
    $clientExe = $ClientExeOverride
    $clientDir = Split-Path -Parent $ClientExeOverride
}
if (-not [string]::IsNullOrWhiteSpace($ClientWorkingDirOverride)) {
    $clientDir = $ClientWorkingDirOverride
}

if (-not [string]::IsNullOrWhiteSpace($ClientExeOverride) -and -not $AllowExternalClientExe.IsPresent) {
    if (-not (Test-PathWithinRoot -CandidatePath $clientExe -WorkspaceRoot $root)) {
        throw "Refusing to launch an external client executable outside the workspace: $clientExe. Stage a local client copy or pass -AllowExternalClientExe to override."
    }
}

$stagedRuneScapeWrapper = $null
$selectedRuneScapeWrapper = Join-Path $clientDir "RuneScape.exe"
$localChildExe = Join-Path $clientDir "rs2client.exe"
$prefer947PatchedDirectClient = (
    $configuredClientBuild -ge 947 -and
    -not $UsePatchedLauncher -and
    -not $explicitWrapperOverride -and
    [string]::Equals((Split-Path -Leaf $clientExe), "rs2client.exe", [System.StringComparison]::OrdinalIgnoreCase)
)
if ($configuredClientBuild -ge 947 -and -not $UsePatchedLauncher -and -not $explicitClientExeOverride -and -not $prefer947PatchedDirectClient) {
    $stagedRuneScapeWrapper = Sync-InstalledRuneScapeWrapper -ClientDirectory $clientDir
    if ([string]::IsNullOrWhiteSpace($stagedRuneScapeWrapper) -or -not (Test-Path $stagedRuneScapeWrapper)) {
        if (Test-Path $selectedRuneScapeWrapper) {
            $stagedRuneScapeWrapper = $selectedRuneScapeWrapper
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($stagedRuneScapeWrapper) -and (Test-Path $stagedRuneScapeWrapper)) {
        $clientExe = $stagedRuneScapeWrapper
    }
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

function Convert-To947DirectClientLaunchArg {
    param(
        [string]$Url,
        [string]$GamePort = ""
    )

    if ([string]::IsNullOrWhiteSpace($Url)) {
        return $Url
    }

    $hostName = Get-UriHostName -Value $Url
    if (
        $configuredClientBuild -lt 947 -or
        -not [string]::Equals($hostName, "rs.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        return $Url
    }

    # The patched local 947 rs2client reaches the login-capable raw-game path
    # only when it stays on the local content/codebase/world bridge.
    $updated = Set-QueryParameter -Url $Url -Name "contentRouteRewrite" -Value "1"
    $updated = Set-QueryParameter -Url $updated -Name "worldUrlRewrite" -Value "1"
    $updated = Set-QueryParameter -Url $updated -Name "codebaseRewrite" -Value "1"
    $updated = Set-QueryParameter -Url $updated -Name "baseConfigSource" -Value "live"
    $updated = Set-QueryParameter -Url $updated -Name "liveCache" -Value "1"
    if (-not [string]::IsNullOrWhiteSpace($GamePort)) {
        $updated = Set-QueryParameter -Url $updated -Name "gamePortOverride" -Value $GamePort
    }
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
        [int]$HttpPort = 0
    )

    if ([string]::IsNullOrWhiteSpace($ConfigUrl)) {
        return $null
    }

    $previewUrl = $ConfigUrl
    $previewUrl = Set-QueryParameter -Url $previewUrl -Name "baseConfigSource" -Value "live"
    $previewUrl = Set-QueryParameter -Url $previewUrl -Name "liveCache" -Value "1"

    $fetchCandidates = @($previewUrl)
    $loopbackUrl = Convert-ToLoopbackJavConfigUrl -Url $previewUrl -HttpPort $HttpPort
    if (-not [string]::IsNullOrWhiteSpace($loopbackUrl) -and $loopbackUrl -ne $previewUrl) {
        $fetchCandidates += $loopbackUrl
    }

    foreach ($candidateUrl in ($fetchCandidates | Select-Object -Unique)) {
        try {
            return (Invoke-WebRequest -Uri $candidateUrl -UseBasicParsing -TimeoutSec 10).Content
        } catch {
            continue
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

function Test-947WorldHostName {
    param([string]$HostName)

    $candidate = $HostName
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $false
    }

    return [bool]($candidate.Trim().ToLowerInvariant() -match '^world[0-9]+[a-z]*\.runescape\.com$|^world\*\.runescape\.com$')
}

function Test-947LobbyHostName {
    param([string]$HostName)

    $candidate = $HostName
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $false
    }

    return [bool]($candidate.Trim().ToLowerInvariant() -match '^lobby[0-9]+[a-z]*\.runescape\.com$|^lobby\*\.runescape\.com$')
}

function Test-947ContentHostName {
    param([string]$HostName)

    $candidate = $HostName
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $false
    }

    return [bool]($candidate.Trim().ToLowerInvariant() -match '^content[a-z0-9-]*\.runescape\.com$|^content\*\.runescape\.com$')
}

function Test-947StartupHostShouldStayRetail {
    param([string]$HostName)

    $candidate = $HostName
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $false
    }

    $normalized = $candidate.Trim().ToLowerInvariant()
    return Test-947WorldHostName -HostName $normalized
}

function Test-947SecureStartupRedirectHost {
    param([string]$HostName)

    $candidate = $HostName
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $false
    }

    $normalized = $candidate.Trim().ToLowerInvariant()
    return (
        (Test-947WorldHostName -HostName $normalized) -or
        (Test-947LobbyHostName -HostName $normalized) -or
        (Test-947ContentHostName -HostName $normalized)
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

        $resolvedHost = Get-UriHostName -Value $candidateValue
        if ([string]::IsNullOrWhiteSpace($resolvedHost)) {
            continue
        }
        if ($resolvedHost -in @("localhost", "127.0.0.1", "::1", "content.runescape.com", "rs.config.runescape.com")) {
            continue
        }
        $hosts += $resolvedHost
    }

    return @($hosts | Select-Object -Unique)
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

function Invoke-DirectPatchedClientLaunch {
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

    function New-DirectPatchPythonArgs {
        param(
            [bool]$EnableStartupHook,
            [bool]$EnableRedirects
        )

        $argsList = @(
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
        if ($EnableStartupHook -and -not [string]::IsNullOrWhiteSpace($StartupHookOutputPath)) {
            $argsList += "--startup-hook-output"
            $argsList += $StartupHookOutputPath
            if ($VerboseStartupHook) {
                $argsList += "--startup-hook-verbose"
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($RsaConfigPath) -and (Test-Path $RsaConfigPath)) {
            $argsList += "--rsa-config"
            $argsList += $RsaConfigPath
            if ($configuredClientBuild -ge 947 -and (Test-Path $originalClientExe)) {
                $argsList += "--js5-rsa-source-exe"
                $argsList += $originalClientExe
            }
        }
        foreach ($clientArg in @($ClientArgumentList | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })) {
            $argsList += ("--client-arg={0}" -f $clientArg)
        }
        foreach ($inlinePatchOffset in $InlinePatchOffsets) {
            $argsList += "--patch-inline-offset"
            $argsList += $inlinePatchOffset
        }
        foreach ($jumpBypassSpec in $JumpBypassSpecs) {
            $argsList += "--patch-jump-bypass"
            $argsList += $jumpBypassSpec
        }
        foreach ($directPatchExtraArg in $DirectPatchExtraArgs) {
            $argsList += $directPatchExtraArg
        }
        if ($EnableRedirects) {
            foreach ($redirectSpec in $RedirectSpecs) {
                $argsList += "--resolve-redirect"
                $argsList += $redirectSpec
            }
        }

        return ,$argsList
    }

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

    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    $usedReducedDirectPatchMode = $false

    function Invoke-DirectPatchAttempt {
        param(
            [bool]$EnableStartupHook,
            [bool]$EnableRedirects
        )

        if (Test-Path $SummaryPath) {
            Remove-Item $SummaryPath -Force -ErrorAction SilentlyContinue
        }
        if (-not [string]::IsNullOrWhiteSpace($StartupHookOutputPath) -and (Test-Path $StartupHookOutputPath)) {
            Remove-Item $StartupHookOutputPath -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $directPatchStdout, $directPatchStderr -Force -ErrorAction SilentlyContinue

        $pythonArgs = New-DirectPatchPythonArgs -EnableStartupHook:$EnableStartupHook -EnableRedirects:$EnableRedirects
        $quotedPythonArgs = @($pythonArgs | ForEach-Object { Quote-ProcessArgument $_ })
        $helperProcess = Start-Process `
            -FilePath $pythonExe `
            -ArgumentList $quotedPythonArgs `
            -WorkingDirectory $WorkspaceRoot `
            -RedirectStandardOutput $directPatchStdout `
            -RedirectStandardError $directPatchStderr `
            -PassThru
        $summaryDeadline = (Get-Date).AddSeconds([Math]::Max(15, $MonitorSeconds))
        while ((Get-Date) -lt $summaryDeadline -and -not (Test-Path $SummaryPath)) {
            $helperStillRunning = Get-Process -Id $helperProcess.Id -ErrorAction SilentlyContinue
            if ($null -eq $helperStillRunning) {
                break
            }

            Start-Sleep -Milliseconds 500
        }

        $helperExitCode = $null
        try {
            $helperProcess.Refresh()
            if ($helperProcess.HasExited) {
                $helperExitCode = $helperProcess.ExitCode
            }
        } catch {}
        $stderrTail = $null
        if (Test-Path $directPatchStderr) {
            $stderrTail = (Get-Content -Path $directPatchStderr -ErrorAction SilentlyContinue | Select-Object -Last 20) -join " | "
        }

        if (-not (Test-Path $SummaryPath)) {
            $terminatedPids = @(Stop-DirectPatchAttemptArtifacts -HelperProcess $helperProcess -LaunchedClientPath $ClientExePath)
            return [pscustomobject]@{
                Success = $false
                FailureMessage = "Direct rs2client patch launch completed without a summary output: $SummaryPath"
                HelperExitCode = $helperExitCode
                StderrTail = $stderrTail
                TerminatedPids = $terminatedPids
            }
        }

        $directPatchLaunchSummary = Read-DirectPatchSummary -Path $SummaryPath
        $bootstrapClientPid = [int]$directPatchLaunchSummary.pid
        $resolvedClientPid = [int]$directPatchLaunchSummary.pid
        $process = $null
        $resolveDeadline = (Get-Date).AddSeconds(10)
        while ((Get-Date) -lt $resolveDeadline -and $null -eq $process) {
            $process = Get-Process -Id $resolvedClientPid -ErrorAction SilentlyContinue
            if ($null -eq $process -and [bool]$directPatchLaunchSummary.processAlive) {
                $process = Resolve-MainClientProcess -BootstrapPid $bootstrapClientPid -TimeoutSeconds 2
            }
            if ($null -eq $process) {
                Start-Sleep -Milliseconds 250
            }
        }
        if ($null -eq $process) {
            $terminatedPids = @(Stop-DirectPatchAttemptArtifacts -HelperProcess $helperProcess -LaunchedClientPath $ClientExePath)
            return [pscustomobject]@{
                Success = $false
                FailureMessage = "Direct rs2client patch launch completed but no live client process could be resolved."
                HelperExitCode = $helperExitCode
                StderrTail = $stderrTail
                TerminatedPids = $terminatedPids
            }
        }

        return [pscustomobject]@{
            Success = $true
            Summary = $directPatchLaunchSummary
            BootstrapClientPid = $bootstrapClientPid
            ResolvedClientPid = $resolvedClientPid
            Process = $process
            HelperProcess = $helperProcess
        }
    }

    $useInitialStartupHook = -not [string]::IsNullOrWhiteSpace($StartupHookOutputPath)
    $useInitialRedirects = $RedirectSpecs.Count -gt 0
    $attempt = Invoke-DirectPatchAttempt -EnableStartupHook:$useInitialStartupHook -EnableRedirects:$useInitialRedirects
    if (-not $attempt.Success -and ($useInitialStartupHook -or $useInitialRedirects)) {
        Write-Host "Direct patch launch retrying without pre-resume Frida startup hook or startup redirects"
        $usedReducedDirectPatchMode = $true
        $attempt = Invoke-DirectPatchAttempt -EnableStartupHook:$false -EnableRedirects:$false
    }
    if (-not $attempt.Success) {
        if (-not [string]::IsNullOrWhiteSpace([string]$attempt.StderrTail)) {
            Write-Host ("Direct patch launch stderr tail: {0}" -f $attempt.StderrTail)
        }
        if ($attempt.TerminatedPids -and $attempt.TerminatedPids.Count -gt 0) {
            Write-Host ("Direct patch launch cleanup terminated pids: {0}" -f ($attempt.TerminatedPids -join ", "))
        }
        if ($null -ne $attempt.HelperExitCode) {
            throw "Direct rs2client patch launch failed with exit code $($attempt.HelperExitCode)."
        }
        throw $attempt.FailureMessage
    }

    return [pscustomobject]@{
        Summary = $attempt.Summary
        BootstrapClientPid = $attempt.BootstrapClientPid
        ResolvedClientPid = $attempt.ResolvedClientPid
        Process = $attempt.Process
        UsedReducedMode = $usedReducedDirectPatchMode
        HelperProcess = $attempt.HelperProcess
    }
}

function Invoke-WrapperFallbackToDirectPatchedClient {
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

    Stop-WrapperLaunchArtifacts -WrapperExePath $WrapperExePath | Out-Null

    $normalizedLaunchArg = Convert-To947DirectClientLaunchArg -Url $LaunchArg
    $effectiveFallbackClientArgs = if ($FallbackClientArgs.Count -gt 0) {
        $FallbackClientArgs
    } else {
        @($normalizedLaunchArg)
    }

    $launch = Invoke-DirectPatchedClientLaunch `
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
        } catch {}
    }

    return $targetPids
}

$script:ConfiguredTlsExtraMitmHosts = @()

if (-not $httpPort) {
    $httpPort = Get-TomlTableScalarValue -Path $serverConfigPath -TableName "networking.ports" -Key "http"
    if (-not $httpPort) {
        $httpPort = "8081"
    }
}
if (-not $gamePort) {
    $gamePort = Get-TomlTableScalarValue -Path $serverConfigPath -TableName "networking.ports" -Key "game"
    if (-not $gamePort) {
        $gamePort = "43594"
    }
}
if (-not $gameBackendPort) {
    $gameBackendPort = Get-TomlTableScalarValue -Path $serverConfigPath -TableName "networking.ports" -Key "gameBackend"
    if (-not $gameBackendPort) {
        $gameBackendPort = "43596"
    }
}
if ($gameBackendPort -eq $gamePort) {
    throw "Canonical no-hosts route requires a public/backend game port split. Found game=$gamePort and gameBackend=$gameBackendPort."
}

if ([string]::IsNullOrWhiteSpace($ConfigUrl)) {
    $loginHost = Get-TomlScalarValue -Path $serverConfigPath -Key "hostname"
    if ([string]::IsNullOrWhiteSpace($loginHost)) {
        $loginHost = "127.0.0.1"
    }
    $loginHost = Normalize-LoopbackHost -HostName $loginHost

    $gameHost = Get-TomlScalarValue -Path $serverConfigPath -Key "gameHostname"
    if ([string]::IsNullOrWhiteSpace($gameHost)) {
        $gameHost = $loginHost
    }
    $gameHost = Normalize-LoopbackHost -HostName $gameHost

    if ($configuredClientBuild -ge 947) {
        # Match the live launcher: keep the visible 947 startup contract
        # retail-shaped and contain it with redirects plus the local 443
        # terminator instead of serving a synthetic local jav_config bridge.
        $ConfigUrl = "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0&baseConfigSource=live&liveCache=1&downloadMetadataSource=original"
    } else {
        $ConfigUrl = "http://${loginHost}:$httpPort/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1&gameHostOverride=$gameHost&gamePortOverride=$gamePort"
    }
}

$downloadMetadataSourceExplicit = $PSBoundParameters.ContainsKey("DownloadMetadataSource")
$existingDownloadMetadataSource = Get-QueryParameterValue -Url $ConfigUrl -Name "downloadMetadataSource"
$resolvedDownloadMetadataSource =
    if ($downloadMetadataSourceExplicit) {
        $DownloadMetadataSource.Trim().ToLowerInvariant()
    } elseif (-not [string]::IsNullOrWhiteSpace($existingDownloadMetadataSource)) {
        $existingDownloadMetadataSource.Trim().ToLowerInvariant()
    } elseif (
        $configuredClientBuild -ge 947 -and
        $prefer947PatchedDirectClient -and
        [string]::Equals((Get-UriHostName -Value $ConfigUrl), "rs.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        # Keep the contained direct 947 retail-shaped startup on the live
        # world-provided download metadata unless the caller explicitly pins a
        # staged family. Rewriting it back to the older staged "original"
        # metadata strands the client on the application-resource loader.
        "live"
    } else {
        $effectiveClientVariant.Trim().ToLowerInvariant()
    }
if (-not [string]::IsNullOrWhiteSpace($resolvedDownloadMetadataSource)) {
    $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "downloadMetadataSource" -Value $resolvedDownloadMetadataSource.Trim().ToLowerInvariant()
}

$runtimeSyncLocalDir = $clientDir
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

if ($configuredClientBuild -ge 947) {
    # Default the 947 launch route according to the selected client family, but
    # respect an explicit caller-provided startup contract so we can still opt
    # into custom snapshot experiments when needed.
    if (-not $configUrlExplicit) {
        $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "hostRewrite" -Value "0"
        $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "lobbyHostRewrite" -Value "0"
        $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "gameHostRewrite" -Value "0"
        if ($ConfigUrl -like "https://rs.config.runescape.com*" -and $prefer947PatchedDirectClient) {
            # Keep the direct 947 startup contract retail-shaped and route it
            # with redirects/runtime repair instead of local config rewrites.
            # Preserve the retail baseline's live base-config + original
            # download metadata pair so the later world-local follow-up stays on
            # the original+live-session contract instead of dropping into the
            # localhost codebase/bootstrap loop.
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "gamePortOverride"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "contentRouteRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "worldUrlRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "codebaseRewrite" -Value "0"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "baseConfigSnapshotPath"
        } elseif ($ConfigUrl -like "https://rs.config.runescape.com*") {
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "gamePortOverride"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "contentRouteRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "worldUrlRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "codebaseRewrite" -Value "0"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "baseConfigSource"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "liveCache"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "baseConfigSnapshotPath"
        } else {
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "contentRouteRewrite" -Value "1"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "worldUrlRewrite" -Value "1"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "codebaseRewrite" -Value "1"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "baseConfigSource" -Value "live"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "liveCache" -Value "1"
        }
    }

    $use947RetailConfigRoute = $ConfigUrl -like "https://rs.config.runescape.com*"
    if ($use947RetailConfigRoute) {
        $startupConfigContent = Get-947StartupConfigContent -ConfigUrl $ConfigUrl -HttpPort ([int]$httpPort)
        if (-not [string]::IsNullOrWhiteSpace($startupConfigContent)) {
            $startupConfigSnapshotReady = Save-947StartupConfigSnapshot -ConfigContent $startupConfigContent -OutputPath $startupConfigSnapshotPath
        }
        if ($prefer947PatchedDirectClient -and -not $configUrlExplicit) {
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "gamePortOverride"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "contentRouteRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "worldUrlRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "codebaseRewrite" -Value "0"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "baseConfigSnapshotPath"
        } elseif (-not $configUrlExplicit) {
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "codebaseRewrite" -Value "0"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "baseConfigSource"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "liveCache"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "baseConfigSnapshotPath"
        }
    } else {
        if ([string]::IsNullOrWhiteSpace((Get-QueryParameterValue -Url $ConfigUrl -Name "codebaseRewrite"))) {
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "codebaseRewrite" -Value "1"
        }
        if ([string]::IsNullOrWhiteSpace((Get-QueryParameterValue -Url $ConfigUrl -Name "baseConfigSource"))) {
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "baseConfigSource" -Value "live"
        }
        if ([string]::IsNullOrWhiteSpace((Get-QueryParameterValue -Url $ConfigUrl -Name "liveCache"))) {
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "liveCache" -Value "1"
        }
        $startupConfigContent = Get-947StartupConfigContent -ConfigUrl $ConfigUrl -HttpPort ([int]$httpPort)
        if (-not [string]::IsNullOrWhiteSpace($startupConfigContent)) {
            if (Save-947StartupConfigSnapshot -ConfigContent $startupConfigContent -OutputPath $startupConfigSnapshotPath) {
                $startupConfigSnapshotReady = $true
                $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "baseConfigSnapshotPath" -Value $startupConfigSnapshotPath
            }
        }
    }
}

$launchArg = $ConfigUrl
$use947RetailConfigRoute = $configuredClientBuild -ge 947 -and $launchArg -like "https://rs.config.runescape.com*"
$use947ContainedLocalBridgeRoute = $configuredClientBuild -ge 947 -and (
    ($launchArg -like "http://127.0.0.1:*" -or $launchArg -like "http://localhost*") -and
    $launchArg -like "*contentRouteRewrite=1*" -and
    $launchArg -like "*worldUrlRewrite=1*" -and
    $launchArg -like "*codebaseRewrite=1*"
)
$shouldLaunch947LobbyProxy = $configuredClientBuild -ge 947 -and ($use947RetailConfigRoute -or $use947ContainedLocalBridgeRoute)
$launchViaRuneScapeWrapper = [string]::Equals((Split-Path -Leaf $clientExe), "RuneScape.exe", [System.StringComparison]::OrdinalIgnoreCase)
$effectiveUseConfigUriArg = $UseConfigUriArg.IsPresent -or $launchViaRuneScapeWrapper
if ($launchViaRuneScapeWrapper) {
    if ($configuredClientBuild -lt 947) {
        $launchArg = Set-QueryParameter -Url $launchArg -Name "worldUrlRewrite" -Value "1"
        $launchArg = Set-QueryParameter -Url $launchArg -Name "baseConfigSource" -Value "compressed"
    } elseif ($use947RetailConfigRoute -and -not $configUrlExplicit) {
        # Match the full live launcher: keep the 947 wrapper startup contract
        # fully retail-shaped so the child stays on the secure splash bootstrap
        # path unless the caller explicitly opts into a local rewrite contract.
        $launchArg = Set-QueryParameter -Url $launchArg -Name "contentRouteRewrite" -Value "0"
        $launchArg = Set-QueryParameter -Url $launchArg -Name "worldUrlRewrite" -Value "0"
        $launchArg = Set-QueryParameter -Url $launchArg -Name "codebaseRewrite" -Value "0"
        $launchArg = Remove-QueryParameter -Url $launchArg -Name "baseConfigSource"
        $launchArg = Remove-QueryParameter -Url $launchArg -Name "liveCache"
        $launchArg = Remove-QueryParameter -Url $launchArg -Name "baseConfigSnapshotPath"
    }
} elseif ($use947RetailConfigRoute -and -not $configUrlExplicit -and -not $prefer947PatchedDirectClient) {
    $launchArg = Convert-To947DirectClientLaunchArg -Url $launchArg -GamePort $gamePort
}
$shouldLaunch947ContentBootstrapProxy = $configuredClientBuild -ge 947 -and
    [int]$httpPort -ne 80 -and
    (
        (
            $launchArg -like "https://rs.config.runescape.com*" -or
            $launchArg -like "http://127.0.0.1:*" -or
            $launchArg -like "http://localhost*"
        ) -and
        $launchArg -like "*contentRouteRewrite=1*"
    )
$clientArgs = @($launchArg)
$directPatchInlinePatchOffsets = @()
$directPatchJumpBypassSpecs = @()
$directPatchExtraArgs = @()
$directPatchLaunchSummary = $null
$wrapperExtraArgs = @()
$wrapperInlinePatchOffsets = @()
$wrapperJumpBypassSpecs = @()
$resolveRedirectSpecs = @()
$useDirectPatchedRs2Client = -not $UsePatchedLauncher -and
    -not $launchViaRuneScapeWrapper -and
    $configuredClientBuild -ge 947 -and
    [string]::Equals((Split-Path -Leaf $clientExe), "rs2client.exe", [System.StringComparison]::OrdinalIgnoreCase)
$use947DirectParamPairArgs = $false
$startupLauncherToken947 = "A234"
$shouldUse947DirectParamPairArgs = $false
if ($shouldUse947DirectParamPairArgs) {
    # Direct patched 947 launches stay on the single config-URL startup family.
    # Converting them to raw param-pair argv flips the client onto the short-
    # lived startup branch that exits before the healthy splash/login path.
    $paramPairArgs947 = @(Convert-947StartupConfigToParamPairArgs -ConfigContent $startupConfigContent -LauncherToken $startupLauncherToken947)
    if ($paramPairArgs947.Count -gt 0) {
        $clientArgs = @($paramPairArgs947)
        $use947DirectParamPairArgs = $true
    }
}
$autoManageGraphicsCompat = $AutoSwitchGraphicsCompat.IsPresent -or
    (($launchViaRuneScapeWrapper -or $useDirectPatchedRs2Client) -and $configuredClientBuild -ge 947)
if ($launchViaRuneScapeWrapper) {
    $clientArgs = @("--configURI=$launchArg")
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
            # 0x7710/0x7734/0x77d8 readiness checks. Keep that fast path only when
            # the normal-path buffers are populated; otherwise fall back into the
            # original compare/enqueue path.
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
} elseif ($effectiveUseConfigUriArg -and -not $use947DirectParamPairArgs) {
    $clientArgs = @("--configURI", $launchArg)
}
if ($configuredClientBuild -ge 947 -and (Test-Path $localChildExe)) {
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
    if ($Force947LoadingStateRebuild) {
        # Some contained splash runs accept an empty +0xbc28 slot because the
        # pair-compare fast path at 0x590cf4 skips the 0x590d5e refresh when
        # the first two metadata values both happen to be zero. NOP that `je`
        # so the chosen slot is rebuilt before 0x594a10 publishes it.
        $directPatchInlinePatchOffsets += "0x590cf4"
    }
    if ($Enable947LoadingStateBuilderTrace) {
        $directPatchExtraArgs += "--loading-state-output-root"
        $directPatchExtraArgs += $directPatchLoadingStateOutputRoot
    }
    if ($Force947RecordStateFromType0) {
        $directPatchExtraArgs += "--resource-gate-output-root"
        $directPatchExtraArgs += $directPatchResourceGateOutputRoot
        $directPatchExtraArgs += "--resource-gate-force-recordstate-from-type0"
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
            Source        = "netstat"
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
        return @(
            Get-NetTCPConnection -State Listen -ErrorAction Stop |
                Where-Object { $_.LocalPort -in $normalizedPorts } |
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
                Where-Object { $_.State -eq "LISTENING" -and $_.LocalPort -in $normalizedPorts }
        )
    }
}

function Get-ListeningProcessIds {
    param([int[]]$Ports)

    return @(
        Get-TcpListenerRecords -Ports $Ports |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
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
                if ($commandLine -notlike "*tls_terminate_proxy.py*" -and $commandLine -notlike "*tcp_proxy.py*") {
                    return $false
                }
                $listenPortMatch = [regex]::Match($commandLine, '(?i)(?:^|\s)--listen-port\s+"?(?<port>\d+)"?')
                $listenPortMatch.Success -and ([int]$listenPortMatch.Groups["port"].Value -eq $ListenPort)
            } |
            Select-Object -ExpandProperty ProcessId -Unique
    )
}

function Wait-ListeningPorts {
    param(
        [int[]]$Ports,
        [int]$TimeoutSeconds = 30,
        [int]$DelayMilliseconds = 250
    )

    $requiredPorts = @($Ports | ForEach-Object { [int]$_ } | Select-Object -Unique)
    if ($requiredPorts.Count -eq 0) {
        return $true
    }

    $retries = [Math]::Max(1, [int][Math]::Ceiling(($TimeoutSeconds * 1000) / $DelayMilliseconds))
    for ($attempt = 0; $attempt -lt $retries; $attempt++) {
        if ($attempt -gt 0) {
            Start-Sleep -Milliseconds $DelayMilliseconds
        }

        $listeningPorts = @(
            Get-TcpListenerRecords -Ports $requiredPorts |
                Select-Object -ExpandProperty LocalPort -Unique
        )

        $allPresent = $true
        foreach ($requiredPort in $requiredPorts) {
            if (-not ($listeningPorts -contains [int]$requiredPort)) {
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
if ($ExtraClientArgs.Count -gt 0) {
    $clientArgs += $ExtraClientArgs
}
$cacheResetResults = @()
$configuredLobbyHost = Get-TomlScalarValue -Path $serverConfigPath -Key "hostname"
if ([string]::IsNullOrWhiteSpace($configuredLobbyHost)) {
    $configuredLobbyHost = "lobby45a.runescape.com"
}
$trustSetup = Ensure-CanonicalMitmTrust -LobbyHost $configuredLobbyHost
$trustState = $trustSetup.TrustState
$script:CanWriteHostsFile = Test-HostsFileWriteAccess -Path $hostsFile
$shouldApplyRetailHostsOverride = $use947RetailConfigRoute -and $configuredClientBuild -lt 947
# Build 947's secure retail route must not rewrite rs.config/content hosts
# back to localhost; clear any stale overrides instead.
Sync-RetailHostsOverride -EnableOverride:$shouldApplyRetailHostsOverride
$startupRouteHosts = @()
if ($configuredClientBuild -ge 947 -and -not [string]::IsNullOrWhiteSpace($startupConfigContent)) {
    $startupRouteHosts = @(Get-947StartupRouteHostsFromConfigContent -ConfigContent $startupConfigContent)
}
$enable947StartupResolveRedirects = $configuredClientBuild -ge 947 -and $use947RetailConfigRoute -and $Force947StartupRouteRedirects
$enable947ContainedRouteRedirects = $configuredClientBuild -ge 947 -and
    $use947RetailConfigRoute -and
    $shouldLaunch947LobbyProxy -and
    -not $Force947StartupRouteRedirects
if ($configuredClientBuild -ge 947 -and $use947RetailConfigRoute) {
    # Keep the visible startup contract retail-shaped by default. Only explicit
    # startup-route experiments should rewrite the startup config itself; the
    # contained local client-only path still needs secure resolve redirects so
    # the later content/lobby/world handoff stays on localhost.
    if ($enable947StartupResolveRedirects) {
        # Match the last clean contained direct baseline: explicit startup-route
        # experiments must keep the content bootstrap host and the secure
        # world/lobby handoff fleet on localhost together.
        $startupRedirectHosts = @(
            @(
                (@(Get-947StartupRouteHostsFromConfigContent -ConfigContent $startupConfigContent) | Where-Object { Test-947SecureStartupRedirectHost -HostName $_ }) +
                    @(Get-947SecureRetailWorldFleetHosts)
            ) |
                Where-Object { $_ -notin @("localhost", "127.0.0.1", "::1", "rs.config.runescape.com") } |
                Select-Object -Unique
        )
        $script:ConfiguredTlsExtraMitmHosts = @(
            $startupRedirectHosts
        )
        $resolveRedirectSpecs = @(
            @(
                $resolveRedirectSpecs +
                    ($startupRedirectHosts | ForEach-Object { "{0}={1}" -f $_, $defaultMitmPrimaryHost })
            ) |
                Select-Object -Unique
        )
        Write-ClientOnlyTrace ("947 startup secure resolve redirects={0}" -f ($resolveRedirectSpecs -join ","))
    } elseif ($enable947ContainedRouteRedirects) {
        # Direct/local-rewrite contracts need real host containment too; the
        # direct patch helper only honors the explicit redirect specs we seed
        # here, and leaving them empty lets content*.runescape.com escape back
        # to retail during sign-in.
        $startupRedirectHosts = @(
            @(
                (@(Get-947StartupRouteHostsFromConfigContent -ConfigContent $startupConfigContent) | Where-Object { Test-947SecureStartupRedirectHost -HostName $_ }) +
                    @(Get-947SecureRetailWorldFleetHosts)
            ) |
                Where-Object { $_ -notin @("localhost", "127.0.0.1", "::1", "rs.config.runescape.com") } |
                Select-Object -Unique
        )
        $script:ConfiguredTlsExtraMitmHosts = @(
            $startupRedirectHosts
        )
        $resolveRedirectSpecs = @(
            @(
                $resolveRedirectSpecs +
                    ($startupRedirectHosts | ForEach-Object { "{0}={1}" -f $_, $defaultMitmPrimaryHost })
            ) |
                Select-Object -Unique
        )
        Write-ClientOnlyTrace ("947 contained route resolve redirects={0}" -f ($resolveRedirectSpecs -join ","))
    } else {
        $script:ConfiguredTlsExtraMitmHosts = @()
        $resolveRedirectSpecs = @($resolveRedirectSpecs | Select-Object -Unique)
        Write-ClientOnlyTrace "947 contained route resolve redirects=<disabled-default>"
    }
}

if ($CefRemoteDebuggingPort) {
    $clientArgs += "--remote-debugging-port=$CefRemoteDebuggingPort"
}

if ($EnableCefLogging) {
    $clientArgs += "--enable-logging"
    $clientArgs += "--log-severity=info"
    $clientArgs += "--log-file=$cefLogFile"
}

Get-Process -Name rs2client,RuneScape -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        taskkill /PID $_.Id /F | Out-Null
    } catch {}
}

Stop-InstalledJagexLauncherProcesses
if ($launchViaRuneScapeWrapper) {
    Stop-WrapperLaunchArtifacts -WrapperExePath $clientExe | Out-Null
}

Start-Sleep -Seconds 1

$serverLaunchResult = $null
Write-ClientOnlyTrace ("server ports check start ports={0},{1}" -f $httpPort, $gameBackendPort)
$serverPortReady = Wait-ListeningPorts -Ports @([int]$httpPort, [int]$gameBackendPort) -TimeoutSeconds 2
if (-not $serverPortReady -and (Test-Path $serverLauncherScript)) {
    $serverLaunchParams = @{}
    if ($configuredClientBuild -ge 947) {
        $serverLaunchParams.EnableRetailRawChecksumPassthrough = $true
        if (-not $AllowRetailJs5Upstream) {
            $serverLaunchParams.EnableRetailLoggedOutJs5Passthrough = $true
        } else {
            $serverLaunchParams.DisableRetailLoggedOutJs5Passthrough = $true
        }
        $serverLaunchParams.SkipHttpFileVerification = $true
    }
    Write-ClientOnlyTrace ("server launch params={0}" -f (($serverLaunchParams.GetEnumerator() | Sort-Object Name | ForEach-Object { "{0}={1}" -f $_.Name, $_.Value }) -join ","))

    $serverLaunchOutput = & $serverLauncherScript @serverLaunchParams
    $serverLaunchText = ($serverLaunchOutput | Out-String).Trim()
    if (-not [string]::IsNullOrWhiteSpace($serverLaunchText)) {
        try {
            $serverLaunchResult = $serverLaunchText | ConvertFrom-Json
        } catch {
            throw "start_server_logged.ps1 returned non-JSON output: $serverLaunchText"
        }
    }

    $serverPortReady = Wait-ListeningPorts -Ports @([int]$httpPort, [int]$gameBackendPort) -TimeoutSeconds 90
    if (-not $serverPortReady) {
        $serverStderrTail = @()
        if ($serverLaunchResult -and -not [string]::IsNullOrWhiteSpace([string]$serverLaunchResult.Stderr) -and (Test-Path ([string]$serverLaunchResult.Stderr))) {
            $serverStderrTail = @(Get-Content -Path ([string]$serverLaunchResult.Stderr) -Tail 40 -ErrorAction SilentlyContinue)
        }
        throw ("Timed out waiting for local server ports {0},{1}. stderrTail={2}" -f $httpPort, $gameBackendPort, ($serverStderrTail -join " | "))
    }
}
Write-ClientOnlyTrace ("server ports ready={0}" -f [bool]$serverPortReady)

$lobbyProxyLauncher = $null
$lobbyProxyLaunchResult = $null
$lobbyProxyReady = $false
$gameProxyLauncher = $null
$gameProxyLaunchResult = $null
$gameProxyReady = $false
$contentBootstrapProxyLauncher = $null
$contentBootstrapProxyReady = $false
$watchdog = $null
if (
    $shouldLaunch947ContentBootstrapProxy -and
    (Test-Path $contentBootstrapProxyScript)
) {
    Write-ClientOnlyTrace "content bootstrap proxy launch begin"
    Remove-Item $contentBootstrapProxyOut, $contentBootstrapProxyErr -Force -ErrorAction SilentlyContinue

    $staleContentBootstrapProxyPids = @(
        Get-ProxyProcessIdsForListenPort -ListenPort 80 |
            Where-Object {
                $process = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $_) -ErrorAction SilentlyContinue
                $null -ne $process -and [string]$process.CommandLine -like "*tcp_proxy.py*"
            }
    )
    foreach ($processId in $staleContentBootstrapProxyPids) {
        try {
            taskkill /PID $processId /F | Out-Null
        } catch {}
    }

    $existingPort80Listeners = @(
        Get-ListeningProcessIds -Ports @(80) |
            Where-Object { $_ -and ($_ -notin $staleContentBootstrapProxyPids) }
    )
    if ($existingPort80Listeners.Count -gt 0) {
        throw ("Cannot start the local content bootstrap proxy on port 80 because it is already in use by pid(s) {0}." -f ($existingPort80Listeners -join ", "))
    }

    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    $contentBootstrapProxyArgs = @(
        $contentBootstrapProxyScript,
        "--listen-host",
        "127.0.0.1",
        "--listen-port",
        "80",
        "--remote-host",
        "127.0.0.1",
        "--remote-port",
        ([string]$httpPort)
    )
    $quotedContentBootstrapProxyArgs = @($contentBootstrapProxyArgs | ForEach-Object { Quote-ProcessArgument $_ })
    $contentBootstrapProxyLauncher = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $quotedContentBootstrapProxyArgs `
        -WorkingDirectory $PSScriptRoot `
        -RedirectStandardOutput $contentBootstrapProxyOut `
        -RedirectStandardError $contentBootstrapProxyErr `
        -PassThru
    Write-ClientOnlyTrace ("content bootstrap proxy launcher pid={0}" -f $contentBootstrapProxyLauncher.Id)

    $contentBootstrapProxyReady = Wait-ListeningPorts -Ports @(80) -TimeoutSeconds 30
    if (-not $contentBootstrapProxyReady) {
        $contentBootstrapProxyStderrTail = $null
        if (Test-Path $contentBootstrapProxyErr) {
            $contentBootstrapProxyStderrTail = ((Get-Content -Path $contentBootstrapProxyErr -ErrorAction SilentlyContinue | Select-Object -Last 20) -join " | ")
        }
        if (-not [string]::IsNullOrWhiteSpace($contentBootstrapProxyStderrTail)) {
            throw ("Timed out waiting for the local content bootstrap proxy on port 80. stderr={0}" -f $contentBootstrapProxyStderrTail)
        }
        throw "Timed out waiting for the local content bootstrap proxy on port 80."
    }
    $contentBootstrapProxyProcessIds = @(Get-ListeningProcessIds -Ports @(80))
    if ($contentBootstrapProxyProcessIds.Count -gt 0) {
        try {
            $contentBootstrapProxyLauncher.Refresh()
        } catch {}
        if ($null -eq $contentBootstrapProxyLauncher -or $contentBootstrapProxyLauncher.HasExited -or $contentBootstrapProxyLauncher.Id -ne [int]$contentBootstrapProxyProcessIds[0]) {
            $contentBootstrapProxyLauncher = Get-Process -Id ([int]$contentBootstrapProxyProcessIds[0]) -ErrorAction SilentlyContinue
        }
    }
    Write-ClientOnlyTrace ("content bootstrap proxy ready={0}" -f [bool]$contentBootstrapProxyReady)
}
if ($shouldLaunch947LobbyProxy -and (Test-Path $lobbyProxyScript)) {
    Write-ClientOnlyTrace "lobby proxy launch begin"
    $lobbyProxyArgs = @{
        ListenHost = "127.0.0.1,::1"
        RemoteHost = "127.0.0.1"
        RemotePort = [int]$gameBackendPort
        SecureGamePassthroughHost = "127.0.0.1"
        SecureGamePassthroughPort = [int]$gamePort
        SecureGameDecryptedHost = "127.0.0.1"
        SecureGameDecryptedPort = [int]$gameBackendPort
        LobbyHost = $configuredLobbyHost
        TlsRemoteHost = "content.runescape.com"
        TlsRemotePort = 443
        TlsConnectHost = "127.0.0.1"
        TlsConnectPort = [int]$httpPort
        TlsRemoteRaw = $true
        MaxSessions = 0
        IdleTimeoutSeconds = 0
    }
    if ($script:ConfiguredTlsExtraMitmHosts.Count -gt 0) {
        $lobbyProxyArgs["TlsExtraMitmHost"] = ($script:ConfiguredTlsExtraMitmHosts -join ",")
    }
    if ($AllowRetailJs5Upstream) {
        $lobbyProxyArgs["AllowRetailJs5Upstream"] = $true
    }

    Remove-Item $lobbyProxyOut, $lobbyProxyErr -Force -ErrorAction SilentlyContinue
    Get-ListeningProcessIds -Ports @(443) | ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {}
    }
    Get-ProxyProcessIdsForListenPort -ListenPort 443 | ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {}
    }
    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    $lobbyProxyOutputDir = Join-Path $root "data\\debug\\lobby-tls-terminator"
    $lobbyProxyPythonArgs = @(
        $tlsTerminateProxyScript,
        "--listen-host",
        "127.0.0.1,::1",
        "--listen-port",
        "443",
        "--remote-host",
        "127.0.0.1",
        "--remote-port",
        ([string]$gameBackendPort),
        "--tls-remote-host",
        "content.runescape.com",
        "--tls-remote-port",
        "443",
        "--tls-extra-mitm-host",
        "rs.config.runescape.com",
        "--pfxfile",
        [string]$trustState.PfxPath,
        "--pfxpassword",
        [string]$trustState.PfxPassword,
        "--output-dir",
        $lobbyProxyOutputDir,
        "--max-sessions",
        "0",
        "--idle-timeout-seconds",
        "0",
        "--socket-timeout",
        "180",
        "--raw-client-byte-cap",
        "0",
        "--raw-client-byte-cap-shutdown-delay-seconds",
        "0",
        "--tls-connect-host",
        "127.0.0.1",
        "--tls-connect-port",
        ([string]$httpPort),
        "--secure-game-passthrough-host",
        "127.0.0.1",
        "--secure-game-passthrough-port",
        ([string]$gamePort),
        "--secure-game-decrypted-host",
        "127.0.0.1",
        "--secure-game-decrypted-port",
        ([string]$gameBackendPort),
        "--tls-remote-raw"
    )
    foreach ($extraMitmHost in @($script:ConfiguredTlsExtraMitmHosts | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
        $lobbyProxyPythonArgs += @("--tls-extra-mitm-host", [string]$extraMitmHost)
    }
    if ($AllowRetailJs5Upstream) {
        $lobbyProxyPythonArgs += "--allow-retail-js5-upstream"
    }
    $quotedLobbyProxyArgs = @($lobbyProxyPythonArgs | ForEach-Object { Quote-ProcessArgument $_ })
    $lobbyProxyLauncher = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $quotedLobbyProxyArgs `
        -WorkingDirectory $PSScriptRoot `
        -RedirectStandardOutput $lobbyProxyOut `
        -RedirectStandardError $lobbyProxyErr `
        -PassThru
    Write-ClientOnlyTrace ("lobby proxy launcher pid={0}" -f $lobbyProxyLauncher.Id)
    Write-ClientOnlyTrace "lobby proxy launch dispatched"

    $lobbyProxyReady = Wait-ListeningPorts -Ports @(443) -TimeoutSeconds 30
    if (-not $lobbyProxyReady) {
        $lobbyProxyStderrTail = $null
        if (Test-Path $lobbyProxyErr) {
            $lobbyProxyStderrTail = ((Get-Content -Path $lobbyProxyErr -ErrorAction SilentlyContinue | Select-Object -Last 20) -join " | ")
        }
        if (-not [string]::IsNullOrWhiteSpace($lobbyProxyStderrTail)) {
            throw ("Timed out waiting for the local lobby TLS terminator on port 443. stderr={0}" -f $lobbyProxyStderrTail)
        }
        throw "Timed out waiting for the local lobby TLS terminator on port 443."
    }
    $lobbyProxyProcessIds = @(Get-ListeningProcessIds -Ports @(443))
    if ($lobbyProxyProcessIds.Count -gt 0) {
        try {
            $lobbyProxyLauncher.Refresh()
        } catch {}
        if ($null -eq $lobbyProxyLauncher -or $lobbyProxyLauncher.HasExited -or $lobbyProxyLauncher.Id -ne [int]$lobbyProxyProcessIds[0]) {
            $lobbyProxyLauncher = Get-Process -Id ([int]$lobbyProxyProcessIds[0]) -ErrorAction SilentlyContinue
        }
    }
    Write-ClientOnlyTrace ("lobby proxy ready={0}" -f [bool]$lobbyProxyReady)

    if (Test-Path $gameProxyScript) {
        Write-ClientOnlyTrace "game proxy launch begin"
        $gameProxyLauncherArgs = @(
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ('"{0}"' -f $gameProxyScript)
        )
        $gameProxyLauncher = Start-Process `
            -FilePath $powershellExe `
            -ArgumentList $gameProxyLauncherArgs `
            -WorkingDirectory $root `
            -WindowStyle Hidden `
            -PassThru
        Write-ClientOnlyTrace ("game proxy launcher pid={0}" -f $gameProxyLauncher.Id)

        $gameProxyReady = Wait-ListeningPorts -Ports @([int]$gamePort) -TimeoutSeconds 30
        if (-not $gameProxyReady) {
            throw ("Timed out waiting for the local game TLS proxy on port {0}." -f $gamePort)
        }
        $gameProxyProcessIds = @(Get-ListeningProcessIds -Ports @([int]$gamePort))
        if ($gameProxyProcessIds.Count -gt 0) {
            $gameProxyLauncher = [pscustomobject]@{
                Id = [int]$gameProxyProcessIds[0]
            }
        }
        Write-ClientOnlyTrace ("game proxy ready={0}" -f [bool]$gameProxyReady)
    }
}

if (
    $configuredClientBuild -ge 947 -and
    $use947RetailConfigRoute -and
    -not $DisableWatchdog.IsPresent -and
    (Test-Path $watchdogScript)
) {
    Remove-Item $watchdogOut, $watchdogErr -Force -ErrorAction SilentlyContinue
    $watchdogArgs = @(
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ('"{0}"' -f $watchdogScript),
        "-CheckIntervalSeconds",
        "2"
    )
    if ($AllowRetailJs5Upstream) {
        $watchdogArgs += "-AllowRetailJs5Upstream"
    }
    $watchdog = Start-Process `
        -FilePath $powershellExe `
        -ArgumentList $watchdogArgs `
        -WorkingDirectory $root `
        -RedirectStandardOutput $watchdogOut `
        -RedirectStandardError $watchdogErr `
        -PassThru
}

$launcherPreferencesResult = $null
$graphicsDeviceResult = $null
$gpuPreferenceResult = $null
if ($autoManageGraphicsCompat -and ($launchViaRuneScapeWrapper -or $useDirectPatchedRs2Client) -and (Test-Path $launcherPreferencesScript)) {
    $preferHighPerformanceGraphics = Test-RecentD3DDeviceRemoved -LogPaths @($directPatchStderr)
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
        $clientExe
        $installedGameClientExe
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
    if ($gpuTargets.Count -gt 0) {
        $preferHighPerformanceGraphics = Test-RecentD3DDeviceRemoved -LogPaths @($directPatchStderr)
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

if ($ResetJagexCache) {
    $cacheResetScript = Join-Path $PSScriptRoot "reset_jagex_cache.ps1"
    $cacheResetJson = & $cacheResetScript -Tag (Get-Date -Format "yyyyMMdd-HHmmss")
    if (-not [string]::IsNullOrWhiteSpace($cacheResetJson)) {
        $cacheResetResults = $cacheResetJson | ConvertFrom-Json
    }
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

$runtimeCacheSyncResult = $null
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
$runtimeUsesRetailStartupConfig = $configuredClientBuild -ge 947 -and $use947RetailConfigRoute
$runtimeAutoSkipCacheSync947Retail = $configuredClientBuild -ge 947 -and $useDirectPatchedRs2Client -and (
    $runtimeUsesRetailStartupConfig -or
    [string]::Equals($resolvedDownloadMetadataSource, "live", [System.StringComparison]::OrdinalIgnoreCase)
)
$runtimeCacheSyncSkippedEffective = [bool]($SkipRuntimeCacheSync.IsPresent -or $runtimeAutoSkipCacheSync947Retail)
if ($runtimeAutoSkipCacheSync947Retail) {
    Write-ClientOnlyTrace "runtime cache sync auto-skipped for 947 live-metadata direct-patched path"
}
if (-not $runtimeCacheSyncSkippedEffective -and $configuredClientBuild -ge 947 -and -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and (Test-Path $runtimeCacheSyncScript)) {
    Write-ClientOnlyTrace "runtime cache sync begin"
    $runtimeCacheSourceDir = Join-Path $root "data\\cache"
    $runtimeCacheTargetDir = Join-Path $env:ProgramData "Jagex\\RuneScape"
    $runtimeAliasSeedingEnabled = $configuredClientBuild -ge 947
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
    $runtimePromoteToFullSync = (
        $runtimeTargetArchiveCount.Count -lt $runtimeSourceFiles.Count -or
        $runtimeHotStubArchiveIds.Count -gt 0 -or
        $runtimeHotMissingReferenceTableArchiveIds.Count -gt 0
    )
    if ($configuredClientBuild -ge 947 -and $runtimeUsesRetailStartupConfig -and $useDirectPatchedRs2Client) {
        $runtimeHotArchiveParityMismatchIds = @(
            foreach ($archiveId in $runtimeHotArchiveIds947) {
                if (-not (Test-RuntimeArchiveMatchesSource -SourceCacheDir $runtimeCacheSourceDir -RuntimeCacheDir $runtimeCacheTargetDir -ArchiveId $archiveId)) {
                    $archiveId
                }
            }
        )
        if ($runtimeHotArchiveParityMismatchIds.Count -gt 0) {
            $runtimePromoteToFullSync = $true
        }
    }
    $runtimeClientManagedHotArchiveSet = $configuredClientBuild -ge 947 -and $runtimeUsesRetailStartupConfig -and $useDirectPatchedRs2Client -and $runtimeMissingHotArchiveIds.Count -eq 0 -and $runtimeHotMissingReferenceTableArchiveIds.Count -eq 0 -and $runtimeHotArchiveParityMismatchIds.Count -eq 0
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
        ((-not $useDirectPatchedRs2Client) -and (-not $runtimeUsesRetailStartupConfig) -and -not $RepairRuntimeHotCache.IsPresent)
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
        Write-Warning ("Runtime cache sync failed but launch will continue: {0}" -f $_.Exception.Message)
    }
    if (Test-Path $runtimeCacheSyncSummary) {
        $runtimeSyncMode = if ($runtimePromoteToFullSync) { "full" } else { "seed-missing" }
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
    }
    Write-ClientOnlyTrace ("runtime cache sync done summary={0}" -f (Test-Path $runtimeCacheSyncSummary))
}

$runtimeHotCacheRepairResult = $null
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
if (
    -not $runtimeCacheSyncSkippedEffective -and
    ($RepairRuntimeHotCache.IsPresent -or $runtimeShouldAutoRepairHotCache947) -and
    -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and
    (Test-Path $runtimeHotCacheRepairScript) -and
    $runtimeHotCacheRepairArchiveIds.Count -gt 0
) {
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
    }
}

$installedRuntimeSyncResult = $null
if (
    $configuredClientBuild -ge 947 -and
    $launchViaRuneScapeWrapper -and
    -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and
    (Test-Path $installedRuntimeSyncTool)
) {
    $installedRuntimeSyncArgs = @(
        $installedRuntimeSyncTool,
        "--config-url",
        $launchArg,
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

if (-not (Test-Path $clientExe)) {
    throw "Client executable not found for variant '$ClientVariant' at $clientExe"
}
if (-not (Test-Path $clientDir)) {
    throw "Client working directory not found at $clientDir"
}

if ($CaptureConsole) {
    Remove-Item $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue
}

if ($EnableCefLogging -and (Test-Path $cefLogFile)) {
    Remove-Item $cefLogFile -Force -ErrorAction SilentlyContinue
}

$startProcessArgs = @{
    FilePath = $clientExe
    ArgumentList = $clientArgs
    WorkingDirectory = $clientDir
    PassThru = $true
}

if ($UsePatchedLauncher) {
    if (-not (Test-Path $launcherExe)) {
        throw "Patched launcher not found at $launcherExe"
    }
    $startProcessArgs.FilePath = $launcherExe
    $startProcessArgs.ArgumentList = @("--configURI", $launchArg)
    $startProcessArgs.WorkingDirectory = $launcherDir
}

if ($CaptureConsole) {
    $startProcessArgs.RedirectStandardOutput = $stdoutLog
    $startProcessArgs.RedirectStandardError = $stderrLog
}

$graphicsHelperResult = $null
$resolvedClientPid = $null
$bootstrapClientPid = $null
$wrapperFallbackToDirectPatched = $false
$wrapperFallbackReason = $null
$wrapperAcceptedInstalledRuntimeChild = $false
$installedRuntimePostLaunchVerifyResult = $null
$directPatchMonitorSeconds = [Math]::Max(300, $StartupDelaySeconds)

if ($useDirectPatchedRs2Client -and (Test-Path $directPatchTool)) {
    Write-ClientOnlyTrace "direct patch launch begin"
    $directLaunch = Invoke-DirectPatchedClientLaunch `
        -ClientExePath $clientExe `
        -WorkingDirectory $clientDir `
        -ClientArgumentList $clientArgs `
        -SummaryPath $directPatchSummary `
        -TracePath $directPatchTrace `
        -StartupHookOutputPath $directPatchStartupHookOutput `
        -DirectPatchToolPath $directPatchTool `
        -WorkspaceRoot $root `
        -RsaConfigPath (Join-Path $root "data\\config\\rsa.toml") `
        -MonitorSeconds $directPatchMonitorSeconds `
        -InlinePatchOffsets $directPatchInlinePatchOffsets `
        -JumpBypassSpecs $directPatchJumpBypassSpecs `
        -DirectPatchExtraArgs $directPatchExtraArgs `
        -RedirectSpecs $resolveRedirectSpecs
    $directPatchLaunchSummary = $directLaunch.Summary
    $bootstrapClientPid = $directLaunch.BootstrapClientPid
    $resolvedClientPid = $directLaunch.ResolvedClientPid
    $process = $directLaunch.Process
    $client = $process
    Write-ClientOnlyTrace ("direct patch launch resolved pid={0}" -f $resolvedClientPid)
} elseif ($launchViaRuneScapeWrapper -and (Test-Path $wrapperRewriteTool)) {
    Write-ClientOnlyTrace "wrapper launch begin"
    $pythonArgs = @(
        $wrapperRewriteTool,
        "--wrapper-exe",
        $clientExe,
        "--config-uri",
        $launchArg,
        "--rsa-config",
        (Join-Path $root "data\\config\\rsa.toml"),
        "--trace-output",
        $wrapperRewriteTrace,
        "--summary-output",
        $wrapperRewriteSummary,
        "--child-hook-output",
        $wrapperRewriteChildHookOutput
    )
    if ($configuredClientBuild -ge 947 -and (Test-Path $originalClientExe)) {
        $pythonArgs += "--js5-rsa-source-exe"
        $pythonArgs += $originalClientExe
    }
    if ($configuredClientBuild -ge 947) {
        $pythonArgs += "--rewrite-scope"
        $pythonArgs += "all"
        $pythonArgs += "--child-hook-duration-seconds"
        $pythonArgs += "120"
        if ($startupConfigSnapshotReady -and (Test-Path $startupConfigSnapshotPath)) {
            $pythonArgs += "--rewrite-config-file"
            $pythonArgs += $startupConfigSnapshotPath
        }
        $wrapperLocalChildOverrideReady = (Test-Path $localChildExe)
        if ($null -ne $installedRuntimeSyncResult) {
            $wrapperLocalChildOverrideReady = $wrapperLocalChildOverrideReady -and [bool]$installedRuntimeSyncResult.wrapperLocalChildOverrideReady
        }
        if ($wrapperLocalChildOverrideReady) {
            $pythonArgs += "--child-exe-override"
            $pythonArgs += $localChildExe
        }
        $acceptedChildRefreshReady = $null -ne $installedRuntimeSyncResult -and
            [bool]$installedRuntimeSyncResult.wrapperLocalChildOverrideReady -and
            [bool]$installedRuntimeSyncResult.installedReadyAfter
        if ($acceptedChildRefreshReady -and -not [string]::IsNullOrWhiteSpace($installedGameClientExe) -and (Test-Path $installedGameClientExe)) {
            $pythonArgs += "--accepted-child-exe"
            $pythonArgs += $installedGameClientExe
        }
    }
    foreach ($wrapperExtraArg in $wrapperExtraArgs) {
        $pythonArgs += "--wrapper-extra-arg=$wrapperExtraArg"
    }
    foreach ($wrapperInlinePatchOffset in $wrapperInlinePatchOffsets) {
        $pythonArgs += "--patch-inline-offset"
        $pythonArgs += $wrapperInlinePatchOffset
    }
    foreach ($wrapperJumpBypassSpec in $wrapperJumpBypassSpecs) {
        $pythonArgs += "--patch-jump-bypass"
        $pythonArgs += $wrapperJumpBypassSpec
    }
    if ($enable947StartupResolveRedirects) {
        $pythonArgs += "--force-secure-retail-startup-redirects"
    }
    foreach ($resolveRedirectSpec in $resolveRedirectSpecs) {
        $pythonArgs += "--resolve-redirect"
        $pythonArgs += $resolveRedirectSpec
    }

    if (Test-Path $wrapperRewriteSummary) {
        Remove-Item $wrapperRewriteSummary -Force -ErrorAction SilentlyContinue
    }

    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    Push-Location $root
    try {
        & $pythonExe @pythonArgs
        $wrapperExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($wrapperExitCode -ne 0) {
        if ((Test-Path $localChildExe) -and (Test-Path $directPatchTool)) {
            $fallback = Invoke-WrapperFallbackToDirectPatchedClient `
                -Reason ("wrapper-rewrite-exit-{0}" -f $wrapperExitCode) `
                -WrapperExePath $clientExe `
                -FallbackClientExePath $localChildExe `
                -WorkingDirectory $clientDir `
                -LaunchArg $launchArg `
                -SummaryPath $directPatchSummary `
                -TracePath $directPatchTrace `
                -StartupHookOutputPath $directPatchStartupHookOutput `
                -DirectPatchToolPath $directPatchTool `
                -WorkspaceRoot $root `
                -RsaConfigPath (Join-Path $root "data\\config\\rsa.toml") `
                -MonitorSeconds $directPatchMonitorSeconds `
                -InlinePatchOffsets $directPatchInlinePatchOffsets `
                -JumpBypassSpecs $directPatchJumpBypassSpecs `
                -RedirectSpecs $resolveRedirectSpecs
            $wrapperFallbackToDirectPatched = $true
            $wrapperFallbackReason = $fallback.Reason
            $directPatchLaunchSummary = $fallback.Launch.Summary
            $bootstrapClientPid = $fallback.Launch.BootstrapClientPid
            $resolvedClientPid = $fallback.Launch.ResolvedClientPid
            $process = $fallback.Launch.Process
        } else {
            Stop-WrapperLaunchArtifacts -WrapperExePath $clientExe | Out-Null
            throw "Wrapper spawn rewrite failed with exit code $wrapperExitCode."
        }
    } else {
        if (-not (Test-Path $wrapperRewriteSummary)) {
            if ((Test-Path $localChildExe) -and (Test-Path $directPatchTool)) {
                $fallback = Invoke-WrapperFallbackToDirectPatchedClient `
                    -Reason "wrapper-summary-missing" `
                    -WrapperExePath $clientExe `
                    -FallbackClientExePath $localChildExe `
                    -WorkingDirectory $clientDir `
                    -LaunchArg $launchArg `
                    -SummaryPath $directPatchSummary `
                    -TracePath $directPatchTrace `
                    -StartupHookOutputPath $directPatchStartupHookOutput `
                    -DirectPatchToolPath $directPatchTool `
                    -WorkspaceRoot $root `
                    -RsaConfigPath (Join-Path $root "data\\config\\rsa.toml") `
                    -MonitorSeconds $directPatchMonitorSeconds `
                    -InlinePatchOffsets $directPatchInlinePatchOffsets `
                    -JumpBypassSpecs $directPatchJumpBypassSpecs `
                    -RedirectSpecs $resolveRedirectSpecs
                $wrapperFallbackToDirectPatched = $true
                $wrapperFallbackReason = $fallback.Reason
                $directPatchLaunchSummary = $fallback.Launch.Summary
                $bootstrapClientPid = $fallback.Launch.BootstrapClientPid
                $resolvedClientPid = $fallback.Launch.ResolvedClientPid
                $process = $fallback.Launch.Process
            } else {
                Stop-WrapperLaunchArtifacts -WrapperExePath $clientExe | Out-Null
                throw "Wrapper spawn rewrite completed without a summary output: $wrapperRewriteSummary"
            }
        } else {
            $wrapperSummary = Get-Content -Path $wrapperRewriteSummary -Raw | ConvertFrom-Json
            $wrapperFailureReason = $null
            $wrapperDonorCommandLine = if (-not [string]::IsNullOrWhiteSpace([string]$wrapperSummary.rewrittenCommandLine)) {
                [string]$wrapperSummary.rewrittenCommandLine
            } else {
                [string]$wrapperSummary.childCommandLine
            }
            $wrapperFallbackClientArgs = Resolve-WrapperFallbackClientArgs `
                -WrapperChildCommandLine $wrapperDonorCommandLine `
                -LaunchArg $launchArg
            if ($null -eq $wrapperSummary.childPid -or [string]::IsNullOrWhiteSpace([string]$wrapperSummary.childPid)) {
                $wrapperFailureReason = "wrapper-child-pid-missing"
            } elseif ($configuredClientBuild -ge 947 -and (Test-Path $localChildExe) -and -not [string]::IsNullOrWhiteSpace([string]$wrapperSummary.childPath)) {
                $expectedChildPath = [System.IO.Path]::GetFullPath($localChildExe)
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
                        $postLaunchVerifyArgs = @(
                            $installedRuntimeSyncTool,
                            "--config-url",
                            $launchArg,
                            "--local-dir",
                            $runtimeSyncLocalDir,
                            "--installed-dir",
                            (Join-Path $env:ProgramData "Jagex\\launcher"),
                            "--summary-output",
                            $installedRuntimePostLaunchVerifySummary,
                            "--timeout-seconds",
                            "30",
                            "--check-only"
                        )
                        if (-not [string]::IsNullOrWhiteSpace($startupConfigSnapshotPath) -and (Test-Path $startupConfigSnapshotPath)) {
                            $postLaunchVerifyArgs += "--config-file"
                            $postLaunchVerifyArgs += $startupConfigSnapshotPath
                        }
                        Remove-Item $installedRuntimePostLaunchVerifySummary -Force -ErrorAction SilentlyContinue
                        $postLaunchVerifyJson = & python @postLaunchVerifyArgs
                        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($postLaunchVerifyJson)) {
                            $installedRuntimePostLaunchVerifyResult = $postLaunchVerifyJson | ConvertFrom-Json
                        }
                        if (
                            $null -ne $installedRuntimePostLaunchVerifyResult -and
                            (
                                (
                                    $acceptedChildRefreshReady -and
                                    [bool]$installedRuntimePostLaunchVerifyResult.wrapperLocalChildOverrideReady
                                ) -or
                                (
                                    $wrapperInstalledRuntimeChildReady -and
                                    [bool]$installedRuntimePostLaunchVerifyResult.wrapperInstalledChildReady
                                )
                            ) -and
                            [bool]$installedRuntimePostLaunchVerifyResult.installedReadyAfter
                        ) {
                            Write-Host ("Wrapper child stayed on synced installed runtime path; accepting child: {0}" -f $actualChildPath)
                            $wrapperAcceptedInstalledRuntimeChild = $true
                        } else {
                            Write-Host ("Wrapper child stayed on installed runtime path, but post-launch verification drifted; forcing direct patched fallback: {0}" -f $actualChildPath)
                            $wrapperFailureReason = "wrapper-installed-runtime-post-launch-drift"
                        }
                    } else {
                        Write-Host ("Wrapper child mismatch after requested override; forcing direct patched fallback: {0}" -f $actualChildPath)
                        $wrapperFailureReason = "wrapper-child-override-mismatch"
                    }
                }
            }

            if (-not [string]::IsNullOrWhiteSpace($wrapperFailureReason) -and (Test-Path $localChildExe) -and (Test-Path $directPatchTool)) {
                $fallback = Invoke-WrapperFallbackToDirectPatchedClient `
                    -Reason $wrapperFailureReason `
                    -WrapperExePath $clientExe `
                    -FallbackClientExePath $localChildExe `
                    -WorkingDirectory $clientDir `
                    -LaunchArg $launchArg `
                    -FallbackClientArgs $wrapperFallbackClientArgs `
                    -SummaryPath $directPatchSummary `
                    -TracePath $directPatchTrace `
                    -StartupHookOutputPath $directPatchStartupHookOutput `
                    -DirectPatchToolPath $directPatchTool `
                    -WorkspaceRoot $root `
                    -RsaConfigPath (Join-Path $root "data\\config\\rsa.toml") `
                    -MonitorSeconds $directPatchMonitorSeconds `
                    -InlinePatchOffsets $directPatchInlinePatchOffsets `
                    -JumpBypassSpecs $directPatchJumpBypassSpecs `
                    -RedirectSpecs $resolveRedirectSpecs
                $wrapperFallbackToDirectPatched = $true
                $wrapperFallbackReason = $fallback.Reason
                $directPatchLaunchSummary = $fallback.Launch.Summary
                $bootstrapClientPid = $fallback.Launch.BootstrapClientPid
                $resolvedClientPid = $fallback.Launch.ResolvedClientPid
                $process = $fallback.Launch.Process
            } else {
                if ($null -eq $wrapperSummary.childPid -or [string]::IsNullOrWhiteSpace([string]$wrapperSummary.childPid)) {
                    Stop-WrapperLaunchArtifacts -WrapperExePath $clientExe | Out-Null
                    throw "Wrapper spawn rewrite completed without a child process id: $wrapperRewriteSummary"
                }
                if ($autoManageGraphicsCompat -and (Test-Path $graphicsDialogHelper)) {
                    $helperJson = & $graphicsDialogHelper -Action Switch -TimeoutSeconds ([Math]::Max(10, $StartupDelaySeconds + 10)) -SummaryOutput $graphicsDialogSummary
                    if (-not [string]::IsNullOrWhiteSpace($helperJson)) {
                        $graphicsHelperResult = $helperJson | ConvertFrom-Json
                    }
                }
                $bootstrapClientPid = [int]$wrapperSummary.wrapperPid
                $resolvedClientPid = [int]$wrapperSummary.childPid
                Stop-InstalledJagexLauncherProcesses
                Start-Sleep -Seconds $StartupDelaySeconds
                $process = Get-Process -Id $resolvedClientPid -ErrorAction SilentlyContinue
                if ($null -eq $process) {
                    $process = Resolve-MainClientProcess -BootstrapPid $bootstrapClientPid -TimeoutSeconds 5
                }
                if ($null -eq $process -and (Test-Path $localChildExe) -and (Test-Path $directPatchTool)) {
                    $fallback = Invoke-WrapperFallbackToDirectPatchedClient `
                        -Reason "wrapper-client-process-missing" `
                        -WrapperExePath $clientExe `
                        -FallbackClientExePath $localChildExe `
                        -WorkingDirectory $clientDir `
                        -LaunchArg $launchArg `
                        -SummaryPath $directPatchSummary `
                        -TracePath $directPatchTrace `
                        -StartupHookOutputPath $directPatchStartupHookOutput `
                        -DirectPatchToolPath $directPatchTool `
                        -WorkspaceRoot $root `
                        -RsaConfigPath (Join-Path $root "data\\config\\rsa.toml") `
                        -MonitorSeconds $directPatchMonitorSeconds `
                        -InlinePatchOffsets $directPatchInlinePatchOffsets `
                        -JumpBypassSpecs $directPatchJumpBypassSpecs `
                        -RedirectSpecs $resolveRedirectSpecs
                    $wrapperFallbackToDirectPatched = $true
                    $wrapperFallbackReason = $fallback.Reason
                    $directPatchLaunchSummary = $fallback.Launch.Summary
                    $bootstrapClientPid = $fallback.Launch.BootstrapClientPid
                    $resolvedClientPid = $fallback.Launch.ResolvedClientPid
                    $process = $fallback.Launch.Process
                }
            }
        }
    }
    $client = $process
    Write-ClientOnlyTrace ("wrapper launch resolved pid={0}" -f $resolvedClientPid)
} else {
    Write-ClientOnlyTrace "plain start-process launch begin"
    $client = Start-Process @startProcessArgs
    $bootstrapClientPid = $client.Id
    if ($autoManageGraphicsCompat -and $launchViaRuneScapeWrapper -and (Test-Path $graphicsDialogHelper)) {
        $helperJson = & $graphicsDialogHelper -Action Switch -TimeoutSeconds ([Math]::Max(10, $StartupDelaySeconds + 10)) -SummaryOutput $graphicsDialogSummary
        if (-not [string]::IsNullOrWhiteSpace($helperJson)) {
            $graphicsHelperResult = $helperJson | ConvertFrom-Json
        }
    }
    if ($launchViaRuneScapeWrapper) {
        Stop-InstalledJagexLauncherProcesses
    }
    Start-Sleep -Seconds $StartupDelaySeconds
    $process = Resolve-MainClientProcess -BootstrapPid $client.Id -TimeoutSeconds 5
    Write-ClientOnlyTrace ("plain start-process resolved pid={0}" -f (if ($process) { $process.Id } else { 0 }))
}

[pscustomobject]@{
    BootstrapClientPid = if ($bootstrapClientPid) { $bootstrapClientPid } else { $client.Id }
    ClientPid = if ($process) { $process.Id } elseif ($resolvedClientPid) { $resolvedClientPid } else { $client.Id }
    ClientAlive = $null -ne $process
    ClientBuild = $configuredClientBuild
    ClientVariant = $effectiveClientVariant
    Disable947InlineNullReadPatches = [bool]$Disable947InlineNullReadPatches.IsPresent
    Disable947JumpBypassGuards = [bool]$Disable947JumpBypassGuards.IsPresent
    AutoSelectedOriginalClient = $false
    MainWindowTitle = if ($process) { $process.MainWindowTitle } else { $null }
    MainWindowHandle = if ($process) { [int64]$process.MainWindowHandle } else { 0 }
    ClientLaunchBinaryKind = if ($useDirectPatchedRs2Client -or $wrapperFallbackToDirectPatched) { "direct-patched-rs2client" } elseif ($launchViaRuneScapeWrapper) { "runescape-wrapper" } elseif ($UsePatchedLauncher) { "patched-launcher" } else { "rs2client" }
    ClientExe = $clientExe
    StagedRuneScapeWrapper = $stagedRuneScapeWrapper
    ClientArgs = $clientArgs
    DownloadMetadataSource = $resolvedDownloadMetadataSource
    DirectPatchSummary = if ($directPatchLaunchSummary) { $directPatchSummary } else { $null }
    DirectPatchStartupHookOutput = if ($directPatchLaunchSummary -and -not [string]::IsNullOrWhiteSpace($directPatchStartupHookOutput)) { $directPatchStartupHookOutput } else { $null }
    DirectPatchInlinePatchOffsets = $directPatchInlinePatchOffsets
    DirectPatchJumpBypassSpecs = $directPatchJumpBypassSpecs
    WrapperExtraArgs = $wrapperExtraArgs
    WrapperInlinePatchOffsets = $wrapperInlinePatchOffsets
    WrapperJumpBypassSpecs = $wrapperJumpBypassSpecs
    WrapperAcceptedInstalledRuntimeChild = $wrapperAcceptedInstalledRuntimeChild
    WrapperFallbackToDirectPatched = $wrapperFallbackToDirectPatched
    WrapperFallbackReason = $wrapperFallbackReason
    LaunchMode = if ($UsePatchedLauncher) { "patched-launcher" } elseif ($useDirectPatchedRs2Client -or $wrapperFallbackToDirectPatched) { "direct-patched-client" } elseif ($launchViaRuneScapeWrapper) { "runescape-wrapper" } else { "direct-client" }
    TlsTrustHealthy = [bool]$trustState.TrustHealthy
    TlsTrustRepaired = [bool]$trustSetup.Repaired
    TlsTrustThumbprint = $trustState.ActiveThumbprint
    TlsTrustSubject = $trustState.ActiveSubject
    TlsDirectLeafTrusted = [bool]$trustState.DirectLeafTrusted
    TlsTrustPfxPath = $trustState.PfxPath
    LobbyProxyScript = if ($lobbyProxyLauncher) { $lobbyProxyScript } else { $null }
    LobbyProxyPid = if ($lobbyProxyLauncher) { [int]$lobbyProxyLauncher.Id } else { $null }
    LobbyProxyPortReady = [bool]$lobbyProxyReady
    LobbyProxyStdout = if ($lobbyProxyLauncher) { $lobbyProxyOut } else { $null }
    LobbyProxyStderr = if ($lobbyProxyLauncher) { $lobbyProxyErr } else { $null }
    ContentBootstrapProxyScript = if ($contentBootstrapProxyLauncher) { $contentBootstrapProxyScript } else { $null }
    ContentBootstrapProxyPid = if ($contentBootstrapProxyLauncher) { [int]$contentBootstrapProxyLauncher.Id } else { $null }
    ContentBootstrapProxyPortReady = [bool]$contentBootstrapProxyReady
    ContentBootstrapProxyStdout = if ($contentBootstrapProxyLauncher) { $contentBootstrapProxyOut } else { $null }
    ContentBootstrapProxyStderr = if ($contentBootstrapProxyLauncher) { $contentBootstrapProxyErr } else { $null }
    GameProxyScript = if ($gameProxyLauncher) { $gameProxyScript } else { $null }
    GameProxyPid = if ($gameProxyLauncher) { [int]$gameProxyLauncher.Id } else { $null }
    GameProxyPortReady = [bool]$gameProxyReady
    WatchdogScript = if ($watchdog) { $watchdogScript } else { $null }
    WatchdogPid = if ($watchdog) { [int]$watchdog.Id } else { $null }
    WatchdogOut = if ($watchdog) { $watchdogOut } else { $null }
    WatchdogErr = if ($watchdog) { $watchdogErr } else { $null }
    DisableWatchdog = [bool]$DisableWatchdog.IsPresent
    ServerLauncherScript = if ($serverLaunchResult) { $serverLauncherScript } else { $null }
    ServerLauncherPid = if ($serverLaunchResult -and $serverLaunchResult.ProcessId) { [int]$serverLaunchResult.ProcessId } else { $null }
    ServerPid = if ($serverLaunchResult -and $serverLaunchResult.ServerPid) { [int]$serverLaunchResult.ServerPid } else { (Get-ListeningProcessIds -Ports @([int]$httpPort, [int]$gameBackendPort) | Select-Object -First 1) }
    ServerPortReady = [bool]$serverPortReady
    ServerStdout = if ($serverLaunchResult) { [string]$serverLaunchResult.Stdout } else { $null }
    ServerStderr = if ($serverLaunchResult) { [string]$serverLaunchResult.Stderr } else { $null }
    ServerLaunchMode = if ($serverLaunchResult) { [string]$serverLaunchResult.LaunchMode } else { $null }
    CacheReset = $cacheResetResults
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
    InstalledRuntimePostLaunchVerifySummary = if ($installedRuntimePostLaunchVerifyResult) { $installedRuntimePostLaunchVerifySummary } else { $null }
    InstalledRuntimePostLaunchVerifyLocalReady = if ($installedRuntimePostLaunchVerifyResult) { [bool]$installedRuntimePostLaunchVerifyResult.localReady } else { $null }
    InstalledRuntimePostLaunchVerifyInstalledReadyBefore = if ($installedRuntimePostLaunchVerifyResult) { [bool]$installedRuntimePostLaunchVerifyResult.installedReadyBefore } else { $null }
    InstalledRuntimePostLaunchVerifyInstalledReadyAfter = if ($installedRuntimePostLaunchVerifyResult) { [bool]$installedRuntimePostLaunchVerifyResult.installedReadyAfter } else { $null }
    InstalledRuntimePostLaunchVerifyPlannedCopyCount = if ($installedRuntimePostLaunchVerifyResult) { [int]$installedRuntimePostLaunchVerifyResult.plannedCopyCount } else { 0 }
    ConsoleCaptured = [bool]$CaptureConsole
    StdoutLog = if ($CaptureConsole) { $stdoutLog } else { $null }
    StderrLog = if ($CaptureConsole) { $stderrLog } else { $null }
    StdoutTail = if ($CaptureConsole -and (Test-Path $stdoutLog)) { Get-Content $stdoutLog | Select-Object -Last 80 } else { @() }
    StderrTail = if ($CaptureConsole -and (Test-Path $stderrLog)) { Get-Content $stderrLog | Select-Object -Last 80 } else { @() }
    CefLogFile = if ($EnableCefLogging) { $cefLogFile } else { $null }
    CefLogTail = if ($EnableCefLogging -and (Test-Path $cefLogFile)) { Get-Content $cefLogFile | Select-Object -Last 120 } else { @() }
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
} | ConvertTo-Json -Depth 3
