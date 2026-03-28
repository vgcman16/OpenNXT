param(
    [string]$ConfigUrl = "https://rs.config.runescape.com/k=5/l=0/jav_config.ws",
    [Nullable[int]]$SeedProtocolBuild = $null,
    [switch]$ForceDownload,
    [switch]$SwitchServerBuild,
    [switch]$PatchLaunchers
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$gradleWrapper = Join-Path $root "gradlew.bat"
$serverConfigPath = Join-Path $root "data\config\server.toml"
$toolsServerConfigPath = Join-Path $root "tools\data\config\server.toml"
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

function Get-TomlTopLevelIntValue {
    param(
        [string]$Path,
        [string]$Key,
        [int]$DefaultValue
    )

    if (-not (Test-Path $Path)) {
        return $DefaultValue
    }

    foreach ($line in (Get-Content $Path)) {
        if ($line -match ("^\s*{0}\s*=\s*(\d+)\s*$" -f [regex]::Escape($Key))) {
            return [int]$Matches[1]
        }
    }

    return $DefaultValue
}

function Set-TomlTopLevelIntValue {
    param(
        [string]$Path,
        [string]$Key,
        [int]$Value
    )

    if (-not (Test-Path $Path)) {
        throw "Cannot update missing TOML file: $Path"
    }

    $updated = $false
    $lines = foreach ($line in (Get-Content $Path)) {
        if (-not $updated -and $line -match ("^\s*{0}\s*=\s*\d+\s*$" -f [regex]::Escape($Key))) {
            $updated = $true
            "{0} = {1}" -f $Key, $Value
        } else {
            $line
        }
    }

    if (-not $updated) {
        $lines = @("{0} = {1}" -f $Key, $Value) + $lines
    }

    Set-Content -Path $Path -Value $lines -Encoding ASCII
}

function Invoke-GradleRunTool {
    param([string]$Arguments)

    Push-Location $root
    try {
        & $gradleWrapper --no-daemon run --args=$Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Gradle tool invocation failed: $Arguments"
        }
    } finally {
        Pop-Location
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
    param([string[]]$ClientDirectories)

    $stagedPaths = @()
    foreach ($directory in $ClientDirectories) {
        if ([string]::IsNullOrWhiteSpace($directory) -or -not (Test-Path $directory)) {
            continue
        }

        $wrapperDestination = Sync-InstalledRuneScapeRuntimeFile -SourcePath $installedGameWrapperExe -ClientDirectory $directory -FileName "RuneScape.exe"
        if (-not [string]::IsNullOrWhiteSpace($wrapperDestination)) {
            $stagedPaths += $wrapperDestination
        }
    }

    return $stagedPaths
}

$detectorConfigUrl = if ($ConfigUrl.Contains("?")) {
    $ConfigUrl
} else {
    ($ConfigUrl + "?binaryType=6")
}

$response = Invoke-WebRequest -UseBasicParsing $detectorConfigUrl
$serverVersionLine = ($response.Content -split "`n" | Where-Object { $_ -match '^server_version=' } | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($serverVersionLine)) {
    throw "Could not find server_version in $detectorConfigUrl"
}

$liveBuild = [int]($serverVersionLine -replace '^server_version=', '')
$resolvedSeedBuild = if ($SeedProtocolBuild) {
    [int]$SeedProtocolBuild
} else {
    Get-TomlTopLevelIntValue -Path $serverConfigPath -Key "build" -DefaultValue 947
}

$clientBuildPath = Join-Path $root ("data\clients\{0}" -f $liveBuild)
$protocolSeedPath = Join-Path $root ("data\prot\{0}" -f $resolvedSeedBuild)
$protocolTargetPath = Join-Path $root ("data\prot\{0}" -f $liveBuild)

if ($ForceDownload -or -not (Test-Path $clientBuildPath)) {
    Invoke-GradleRunTool -Arguments ("run-tool client-downloader --config-url={0}" -f $ConfigUrl)
}

$patchArguments = "run-tool client-patcher --version {0}" -f $liveBuild
if (-not $PatchLaunchers) {
    $patchArguments += " --skip-launcher"
}
Invoke-GradleRunTool -Arguments $patchArguments

$stagedWrapperPaths = @()
if ($liveBuild -gt 946) {
    $stagedWrapperPaths = Sync-InstalledRuneScapeWrapper -ClientDirectories @(
        (Join-Path $clientBuildPath "win64c\original"),
        (Join-Path $clientBuildPath "win64c\patched")
    )
}

$protocolSeeded = $false
if (-not (Test-Path $protocolTargetPath)) {
    if (-not (Test-Path $protocolSeedPath)) {
        throw "Protocol seed build path does not exist: $protocolSeedPath"
    }

    if ($resolvedSeedBuild -eq $liveBuild) {
        throw "Protocol seed build equals live build $liveBuild, but $protocolTargetPath is missing."
    }

    Copy-Item -Path $protocolSeedPath -Destination $protocolTargetPath -Recurse
    $protocolSeeded = $true
}

if ($SwitchServerBuild) {
    Set-TomlTopLevelIntValue -Path $serverConfigPath -Key "build" -Value $liveBuild
    if (Test-Path $toolsServerConfigPath) {
        Set-TomlTopLevelIntValue -Path $toolsServerConfigPath -Key "build" -Value $liveBuild
    }
}

[pscustomobject]@{
    LiveBuild = $liveBuild
    ConfigUrl = $ConfigUrl
    DetectorConfigUrl = $detectorConfigUrl
    ClientBuildPath = $clientBuildPath
    Win64cPatchedClient = Join-Path $clientBuildPath "win64c\patched\rs2client.exe"
    Win64cOriginalWrapper = Join-Path $clientBuildPath "win64c\original\RuneScape.exe"
    Win64cPatchedWrapper = Join-Path $clientBuildPath "win64c\patched\RuneScape.exe"
    StagedWrapperPaths = $stagedWrapperPaths
    ProtocolSeedBuild = $resolvedSeedBuild
    ProtocolPath = $protocolTargetPath
    ProtocolSeeded = $protocolSeeded
    SwitchedServerBuild = $SwitchServerBuild.IsPresent
    MainServerConfig = $serverConfigPath
    ToolsServerConfig = if (Test-Path $toolsServerConfigPath) { $toolsServerConfigPath } else { $null }
    LauncherPatchAttempted = $PatchLaunchers.IsPresent
} | ConvertTo-Json -Depth 3
