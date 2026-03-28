$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$serverConfigPath = Join-Path $root "data\config\server.toml"

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
$effectiveClientVariant = if ($configuredClientBuild -gt 946) { "original" } else { "patched" }
$clientDir = Join-Path $root ("data\\clients\\{0}\\win64c\\{1}" -f $configuredClientBuild, $effectiveClientVariant)
$clientExe = Join-Path $clientDir "rs2client.exe"
$configUrl = "http://lobby45a.runescape.com:8081/jav_config.ws?binaryType=6&hostRewrite=0&gameHostOverride=lobby45a.runescape.com&downloadMetadataSource=patched"

Get-Process -Name rs2client -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        taskkill /PID $_.Id /F | Out-Null
    } catch {
    }
}

$process = Start-Process -FilePath $clientExe `
    -ArgumentList @($configUrl) `
    -WorkingDirectory $clientDir `
    -PassThru

[pscustomobject]@{
    ProcessId = $process.Id
    ClientBuild = $configuredClientBuild
    ClientVariant = $effectiveClientVariant
    ClientExe = $clientExe
    ConfigUrl = $configUrl
} | ConvertTo-Json -Depth 3
