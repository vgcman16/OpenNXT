param(
    [string]$ConfigUrl = "",
    [int]$StartupDelaySeconds = 15,
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging,
    [switch]$CaptureConsole,
    [switch]$UsePatchedLauncher,
    [string]$ClientExeOverride = "",
    [string]$ClientWorkingDirOverride = "",
    [switch]$AllowExternalClientExe,
    [switch]$UseConfigUriArg,
    [string[]]$ExtraClientArgs = @(),
    [string]$ClientVariant = "patched",
    [switch]$ResetJagexCache,
    [switch]$RepairRuntimeHotCache,
    [string]$DownloadMetadataSource = "patched",
    [switch]$AutoSwitchGraphicsCompat,
    [switch]$UseRuneScapeWrapper
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
$graphicsDialogHelper = Join-Path $PSScriptRoot "invoke_runescape_graphics_dialog_action.ps1"
$launcherPreferencesScript = Join-Path $PSScriptRoot "set_runescape_launcher_preferences.ps1"
$windowsGpuPreferenceScript = Join-Path $PSScriptRoot "set_windows_gpu_preference.ps1"
$runtimeCacheSyncScript = Join-Path $PSScriptRoot "sync_runescape_runtime_cache.ps1"
$runtimeHotCacheRepairScript = Join-Path $PSScriptRoot "repair_runescape_runtime_hot_cache.ps1"
$installedRuntimeSyncTool = Join-Path $PSScriptRoot "sync_runescape_installed_runtime.py"
$directPatchTrace = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-client-only.jsonl"
$directPatchSummary = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-client-only.json"
$wrapperRewriteTrace = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-client-only.jsonl"
$wrapperRewriteSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-client-only.json"
$wrapperRewriteChildHookOutput = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-client-only-child-hook.jsonl"
$graphicsDialogSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-graphics-dialog.json"
$launcherPreferencesSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-launcher-preferences.json"
$gpuPreferenceSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-gpu-preference.json"
$runtimeCacheSyncSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-runtime-cache-sync.json"
$runtimeHotCacheRepairSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-runtime-hot-cache-repair.json"
$installedRuntimeSyncSummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-installed-runtime-sync.json"
$installedRuntimePostLaunchVerifySummary = Join-Path $root "data\\debug\\wrapper-spawn-rewrite\\latest-installed-runtime-post-launch-check.json"
$startupConfigSnapshotPath = Join-Path $root "tmp-947-startup-config-client-only.ws"
$directPatchStartupHookOutput = Join-Path $root "data\\debug\\direct-rs2client-patch\\latest-client-only-hook.jsonl"
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
        }
        if (-not [string]::IsNullOrWhiteSpace($RsaConfigPath) -and (Test-Path $RsaConfigPath)) {
            $argsList += "--rsa-config"
            $argsList += $RsaConfigPath
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
        if ($EnableRedirects) {
            foreach ($redirectSpec in $RedirectSpecs) {
                $argsList += "--resolve-redirect"
                $argsList += $redirectSpec
            }
        }

        return ,$argsList
    }

    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    $directPatchExitCode = $null
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

        $pythonArgs = New-DirectPatchPythonArgs -EnableStartupHook:$EnableStartupHook -EnableRedirects:$EnableRedirects
        Push-Location $WorkspaceRoot
        try {
            & $pythonExe @pythonArgs
            return $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }

    $directPatchExitCode = Invoke-DirectPatchAttempt -EnableStartupHook:(-not [string]::IsNullOrWhiteSpace($StartupHookOutputPath)) -EnableRedirects:($RedirectSpecs.Count -gt 0)
    if ($directPatchExitCode -ne 0 -and ((-not [string]::IsNullOrWhiteSpace($StartupHookOutputPath)) -or $RedirectSpecs.Count -gt 0)) {
        Write-Host "Direct patch launch retrying without pre-resume Frida startup hook or startup redirects"
        $usedReducedDirectPatchMode = $true
        $directPatchExitCode = Invoke-DirectPatchAttempt -EnableStartupHook:$false -EnableRedirects:$false
    }
    if ($directPatchExitCode -ne 0) {
        throw "Direct rs2client patch launch failed with exit code $directPatchExitCode."
    }

    if (-not (Test-Path $SummaryPath)) {
        throw "Direct rs2client patch launch completed without a summary output: $SummaryPath"
    }

    $directPatchLaunchSummary = Get-Content -Path $SummaryPath -Raw | ConvertFrom-Json
    $bootstrapClientPid = [int]$directPatchLaunchSummary.pid
    $resolvedClientPid = [int]$directPatchLaunchSummary.pid
    $process = Get-Process -Id $resolvedClientPid -ErrorAction SilentlyContinue
    if ($null -eq $process -and [bool]$directPatchLaunchSummary.processAlive) {
        $process = Resolve-MainClientProcess -BootstrapPid $bootstrapClientPid -TimeoutSeconds 5
    }
    if ($null -eq $process) {
        throw "Direct rs2client patch launch completed but no live client process could be resolved."
    }

    return [pscustomobject]@{
        Summary = $directPatchLaunchSummary
        BootstrapClientPid = $bootstrapClientPid
        ResolvedClientPid = $resolvedClientPid
        Process = $process
        UsedReducedMode = $usedReducedDirectPatchMode
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

if ([string]::IsNullOrWhiteSpace($ConfigUrl)) {
    $httpPort = Get-TomlTableScalarValue -Path $serverConfigPath -TableName "networking.ports" -Key "http"
    if (-not $httpPort) {
        $httpPort = "8081"
    }
    $gamePort = Get-TomlTableScalarValue -Path $serverConfigPath -TableName "networking.ports" -Key "game"
    if (-not $gamePort) {
        $gamePort = "43594"
    }
    $gameBackendPort = Get-TomlTableScalarValue -Path $serverConfigPath -TableName "networking.ports" -Key "gameBackend"
    if (-not $gameBackendPort) {
        $gameBackendPort = "43596"
    }
    if ($gameBackendPort -eq $gamePort) {
        throw "Canonical no-hosts route requires a public/backend game port split. Found game=$gamePort and gameBackend=$gameBackendPort."
    }

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
        # Keep the direct 947 client on the same secure startup
        # transport family as retail splash. We can still opt into the local
        # jav_config route explicitly when diagnosing later phases.
        $ConfigUrl = "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0"
    } else {
        $ConfigUrl = "http://${loginHost}:$httpPort/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1&gameHostOverride=$gameHost&gamePortOverride=$gamePort"
    }
}

if (-not $httpPort) {
    $httpPort = Get-TomlTableScalarValue -Path $serverConfigPath -TableName "networking.ports" -Key "http"
    if (-not $httpPort) {
        $httpPort = "8081"
    }
}

$downloadMetadataSourceExplicit = $PSBoundParameters.ContainsKey("DownloadMetadataSource")
$existingDownloadMetadataSource = Get-QueryParameterValue -Url $ConfigUrl -Name "downloadMetadataSource"
$resolvedDownloadMetadataSource =
    if ($downloadMetadataSourceExplicit) {
        $DownloadMetadataSource.Trim().ToLowerInvariant()
    } elseif (-not [string]::IsNullOrWhiteSpace($existingDownloadMetadataSource)) {
        $existingDownloadMetadataSource.Trim().ToLowerInvariant()
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
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "gamePortOverride"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "contentRouteRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "worldUrlRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "codebaseRewrite" -Value "0"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "baseConfigSource"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "liveCache"
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
        if ($prefer947PatchedDirectClient) {
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "gamePortOverride"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "contentRouteRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "worldUrlRewrite" -Value "0"
            $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "codebaseRewrite" -Value "0"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "baseConfigSource"
            $ConfigUrl = Remove-QueryParameter -Url $ConfigUrl -Name "liveCache"
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
                $ConfigUrl = Set-QueryParameter -Url $ConfigUrl -Name "baseConfigSnapshotPath" -Value $startupConfigSnapshotPath
            }
        }
    }
}

$launchArg = $ConfigUrl
$use947RetailConfigRoute = $configuredClientBuild -ge 947 -and $launchArg -like "https://rs.config.runescape.com*"
$launchViaRuneScapeWrapper = [string]::Equals((Split-Path -Leaf $clientExe), "RuneScape.exe", [System.StringComparison]::OrdinalIgnoreCase)
$effectiveUseConfigUriArg = $UseConfigUriArg.IsPresent -or $launchViaRuneScapeWrapper
if ($launchViaRuneScapeWrapper) {
    if ($configuredClientBuild -lt 947) {
        $launchArg = Set-QueryParameter -Url $launchArg -Name "worldUrlRewrite" -Value "1"
        $launchArg = Set-QueryParameter -Url $launchArg -Name "baseConfigSource" -Value "compressed"
    } elseif ($use947RetailConfigRoute -and -not $configUrlExplicit) {
        # Match the full live launcher: keep the 947 wrapper's visible
        # world/content startup contract retail-shaped, but serve the codebase
        # through the local stack so splash bootstrap can progress into the
        # real pre-login path.
        $launchArg = Set-QueryParameter -Url $launchArg -Name "codebaseRewrite" -Value "1"
    }
} elseif ($use947RetailConfigRoute -and -not $configUrlExplicit -and -not $prefer947PatchedDirectClient) {
    $launchArg = Convert-To947DirectClientLaunchArg -Url $launchArg -GamePort $gamePort
}
$clientArgs = @($launchArg)
$directPatchInlinePatchOffsets = @()
$directPatchJumpBypassSpecs = @()
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
} elseif ($effectiveUseConfigUriArg -and -not $use947DirectParamPairArgs) {
    $clientArgs = @("--configURI", $launchArg)
}
if ($configuredClientBuild -ge 947 -and (Test-Path $localChildExe)) {
    $directPatchInlinePatchOffsets += "0x590001"
    $directPatchInlinePatchOffsets += "0x5916c3"
    $directPatchInlinePatchOffsets += "0x5916f0"
    $directPatchInlinePatchOffsets += "0x591712"
    $directPatchInlinePatchOffsets += "0x591719"
    $directPatchJumpBypassSpecs += "0x59002d:0x5900a5"
    $directPatchJumpBypassSpecs += "0x590c72:0x590dcb"
    if ($use947RetailConfigRoute) {
        # Keep the secure retail-config route on the small startup dereference
        # guard set. The donor/wrapper fallback path still needs the early
        # 0x72ad28 guard, but we continue to avoid the later compat cluster.
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
Sync-RetailHostsOverride -EnableOverride:$use947RetailConfigRoute
$startupRouteHosts = @()
if ($configuredClientBuild -ge 947 -and -not [string]::IsNullOrWhiteSpace($startupConfigContent)) {
    $startupRouteHosts = @(Get-947StartupRouteHostsFromConfigContent -ConfigContent $startupConfigContent)
}
if ($configuredClientBuild -ge 947 -and $use947RetailConfigRoute -and -not $useDirectPatchedRs2Client -and -not $script:CanWriteHostsFile) {
    # Keep the visible startup contract retail-shaped, but when we cannot rely
    # on the Windows hosts file we still need wrapper/original startup hosts to
    # land on the local MITM stack instead of escaping to retail during splash
    # bootstrap. The direct 947 patched path must stay fully retail-shaped here
    # or it reintroduces the early raw bootstrap before login.
    $startupRedirectHosts = @(
        @(Get-947StartupWorldMitmHostsFromConfigContent -ConfigContent $startupConfigContent) |
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

$launcherPreferencesResult = $null
$gpuPreferenceResult = $null
if ($autoManageGraphicsCompat -and ($launchViaRuneScapeWrapper -or $useDirectPatchedRs2Client) -and (Test-Path $launcherPreferencesScript)) {
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
        $clientExe
        $installedGameClientExe
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
    if ($gpuTargets.Count -gt 0) {
        $gpuPreferenceJson = & $windowsGpuPreferenceScript -ExecutablePath $gpuTargets -Preference "high-performance" -SummaryOutput $gpuPreferenceSummary
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

$runtimeCacheSyncResult = $null
$runtimeCopiedHotArchiveIds = @()
$runtimeAutoRepairReason = $null
$runtimeShouldAutoRepairHotCache947 = $false
$runtimeHotCacheRepairArchiveIds = @()
$runtimeHotStubArchiveIds = @()
$runtimeShouldPreserveHotArchiveSet = $false
if ($configuredClientBuild -ge 947 -and -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and (Test-Path $runtimeCacheSyncScript)) {
    $runtimeCacheSourceDir = Join-Path $root "data\\cache"
    $runtimeCacheTargetDir = Join-Path $env:ProgramData "Jagex\\RuneScape"
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
    $runtimeUsesRetailStartupConfig = $configuredClientBuild -ge 947 -and $use947RetailConfigRoute
    $runtimePromoteToFullSync = $runtimeUsesRetailStartupConfig -or ($useDirectPatchedRs2Client -and ($runtimeTargetFiles.Count -lt $runtimeSourceFiles.Count -or $runtimeHotStubArchiveIds.Count -gt 0))
    $runtimeClientManagedHotArchiveSet = $configuredClientBuild -ge 947 -and $runtimeUsesRetailStartupConfig -and $useDirectPatchedRs2Client -and $runtimeMissingHotArchiveIds.Count -eq 0
    $runtimeCacheSyncParameters = @{
        SourceCacheDir = $runtimeCacheSourceDir
        RuntimeCacheDir = $runtimeCacheTargetDir
        SummaryOutput  = $runtimeCacheSyncSummary
        NoOutput       = $true
    }
    $runtimeShouldPreserveHotArchiveSet = $runtimeClientManagedHotArchiveSet -or ((-not $useDirectPatchedRs2Client) -and (-not $runtimeUsesRetailStartupConfig) -and -not $RepairRuntimeHotCache.IsPresent)
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
        $runtimeSyncMode = if ($runtimePromoteToFullSync) { "full" } else { "seed-missing" }
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
    }
}

$runtimeHotCacheRepairResult = $null
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
if (
    ($RepairRuntimeHotCache.IsPresent -or $runtimeShouldAutoRepairHotCache947) -and
    -not [string]::IsNullOrWhiteSpace($env:ProgramData) -and
    (Test-Path $runtimeHotCacheRepairScript) -and
    $runtimeHotCacheRepairArchiveIds.Count -gt 0
) {
    & $runtimeHotCacheRepairScript `
        -RuntimeCacheDir (Join-Path $env:ProgramData "Jagex\\RuneScape") `
        -ArchiveIds $runtimeHotCacheRepairArchiveIds `
        -IncludeAuxiliaryFiles `
        -SummaryOutput $runtimeHotCacheRepairSummary `
        -NoOutput
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
    if ($null -ne $installedRuntimeSyncResult -and -not [bool]$installedRuntimeSyncResult.localReady) {
        throw "Installed runtime sync refused to continue because the staged local 947 client family does not match the live manifest."
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

if ($useDirectPatchedRs2Client -and (Test-Path $directPatchTool)) {
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
        -MonitorSeconds $StartupDelaySeconds `
        -InlinePatchOffsets $directPatchInlinePatchOffsets `
        -JumpBypassSpecs $directPatchJumpBypassSpecs `
        -RedirectSpecs $resolveRedirectSpecs
    $directPatchLaunchSummary = $directLaunch.Summary
    $bootstrapClientPid = $directLaunch.BootstrapClientPid
    $resolvedClientPid = $directLaunch.ResolvedClientPid
    $process = $directLaunch.Process
    $client = $process
} elseif ($launchViaRuneScapeWrapper -and (Test-Path $wrapperRewriteTool)) {
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
    if ($configuredClientBuild -ge 947) {
        $pythonArgs += "--rewrite-scope"
        $pythonArgs += "all"
        $pythonArgs += "--child-hook-duration-seconds"
        $pythonArgs += "20"
        if (Test-Path $localChildExe) {
            $pythonArgs += "--child-exe-override"
            $pythonArgs += $localChildExe
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
                -MonitorSeconds $StartupDelaySeconds `
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
                    -MonitorSeconds $StartupDelaySeconds `
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
                    $installedRuntimeReady = $null -ne $installedRuntimeSyncResult -and
                        [bool]$installedRuntimeSyncResult.localReady -and
                        [bool]$installedRuntimeSyncResult.installedReadyAfter
                    if (
                        $installedRuntimeReady -and
                        -not [string]::IsNullOrWhiteSpace($installedRuntimeChildPath) -and
                        [string]::Equals($installedRuntimeChildPath, $actualChildPath, [System.StringComparison]::OrdinalIgnoreCase)
                    ) {
                        Write-Host ("Wrapper child stayed on synced installed runtime path; accepting child: {0}" -f $actualChildPath)
                        $wrapperAcceptedInstalledRuntimeChild = $true
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
                    -MonitorSeconds $StartupDelaySeconds `
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
                        -MonitorSeconds $StartupDelaySeconds `
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
} else {
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
}

[pscustomobject]@{
    BootstrapClientPid = if ($bootstrapClientPid) { $bootstrapClientPid } else { $client.Id }
    ClientPid = if ($process) { $process.Id } elseif ($resolvedClientPid) { $resolvedClientPid } else { $client.Id }
    ClientAlive = $null -ne $process
    ClientBuild = $configuredClientBuild
    ClientVariant = $effectiveClientVariant
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
    CacheReset = $cacheResetResults
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
    ConsoleCaptured = [bool]$CaptureConsole
    StdoutLog = if ($CaptureConsole) { $stdoutLog } else { $null }
    StderrLog = if ($CaptureConsole) { $stderrLog } else { $null }
    StdoutTail = if ($CaptureConsole -and (Test-Path $stdoutLog)) { Get-Content $stdoutLog | Select-Object -Last 80 } else { @() }
    StderrTail = if ($CaptureConsole -and (Test-Path $stderrLog)) { Get-Content $stderrLog | Select-Object -Last 80 } else { @() }
    CefLogFile = if ($EnableCefLogging) { $cefLogFile } else { $null }
    CefLogTail = if ($EnableCefLogging -and (Test-Path $cefLogFile)) { Get-Content $cefLogFile | Select-Object -Last 120 } else { @() }
    GraphicsDialogSummary = if ($graphicsHelperResult) { $graphicsDialogSummary } else { $null }
    GraphicsDialogInvoked = if ($graphicsHelperResult) { [bool]$graphicsHelperResult.Invoked } else { $null }
    LauncherPreferencesSummary = if ($launcherPreferencesResult) { $launcherPreferencesSummary } else { $null }
    LauncherCompatibilityForced = if ($launcherPreferencesResult) { $launcherPreferencesResult.After.Compatibility } else { $null }
    LauncherPreferencesChangedKeys = if ($launcherPreferencesResult) { @($launcherPreferencesResult.ChangedKeys) } else { @() }
    GpuPreferenceSummary = if ($gpuPreferenceResult) { $gpuPreferenceSummary } else { $null }
    GpuPreferenceChangedPaths = if ($gpuPreferenceResult) { @($gpuPreferenceResult.ChangedPaths) } else { @() }
    GpuPreferenceTargetPaths = if ($gpuPreferenceResult) { @($gpuPreferenceResult.Entries | ForEach-Object { $_.ExecutablePath }) } else { @() }
} | ConvertTo-Json -Depth 3
