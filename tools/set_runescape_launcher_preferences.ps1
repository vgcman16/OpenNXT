param(
    [ValidateSet("default", "true", "false")]
    [string]$Compatibility = "true",
    [string]$GraphicsDevice = "",
    [switch]$DontAskAgain,
    [switch]$ClearDontAskAgain,
    [string]$PreferencesPath = "C:\ProgramData\Jagex\launcher\preferences.cfg",
    [string]$SummaryOutput = ""
)

$ErrorActionPreference = "Stop"

function Get-PreferenceMap {
    param([string[]]$Lines)

    $result = [ordered]@{}
    foreach ($line in $Lines) {
        if ($line -match '^\s*([^=\s]+)\s*=(.*)$') {
            $result[$Matches[1]] = $Matches[2].Trim()
        }
    }

    return $result
}

function Set-PreferenceValue {
    param(
        [string[]]$Lines,
        [string]$Key,
        [string]$Value
    )

    $updated = $false
    $result = New-Object System.Collections.Generic.List[string]
    $pattern = "^\s*{0}\s*=" -f [regex]::Escape($Key)

    foreach ($line in $Lines) {
        if ($line -match $pattern) {
            if (-not $updated) {
                $result.Add(("{0}={1}" -f $Key, $Value))
                $updated = $true
            }
            continue
        }

        $result.Add($line)
    }

    if (-not $updated) {
        $result.Add(("{0}={1}" -f $Key, $Value))
    }

    return $result.ToArray()
}

function Remove-PreferenceValue {
    param(
        [string[]]$Lines,
        [string]$Key
    )

    $result = New-Object System.Collections.Generic.List[string]
    $pattern = "^\s*{0}\s*=" -f [regex]::Escape($Key)

    foreach ($line in $Lines) {
        if ($line -match $pattern) {
            continue
        }

        $result.Add($line)
    }

    return $result.ToArray()
}

function Normalize-PreferenceScalar {
    param([object]$Value)

    if ($null -eq $Value) {
        return ""
    }

    $text = $Value.ToString().Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        return ""
    }

    switch -Regex ($text.ToLowerInvariant()) {
        "^(true|false|default)$" { return $Matches[1] }
        default { return $text.ToLowerInvariant() }
    }
}

$beforeLines = if (Test-Path $PreferencesPath) { @(Get-Content -Path $PreferencesPath) } else { @() }
$updatedLines = @($beforeLines)
$normalizedCompatibility = Normalize-PreferenceScalar -Value $Compatibility
$updatedLines = Set-PreferenceValue -Lines $updatedLines -Key "compatibility" -Value $normalizedCompatibility
if ($DontAskAgain) {
    $updatedLines = Set-PreferenceValue -Lines $updatedLines -Key "dont_ask_graphics" -Value "1"
} elseif ($ClearDontAskAgain) {
    $updatedLines = Remove-PreferenceValue -Lines $updatedLines -Key "dont_ask_graphics"
}
$normalizedGraphicsDevice = Normalize-PreferenceScalar -Value $GraphicsDevice
if (-not [string]::IsNullOrWhiteSpace($normalizedGraphicsDevice)) {
    if ($normalizedGraphicsDevice -eq "default") {
        $updatedLines = Remove-PreferenceValue -Lines $updatedLines -Key "graphics_device"
    } else {
        $updatedLines = Set-PreferenceValue -Lines $updatedLines -Key "graphics_device" -Value $normalizedGraphicsDevice
    }
}

$preferencesDirectory = Split-Path -Parent $PreferencesPath
if (-not [string]::IsNullOrWhiteSpace($preferencesDirectory)) {
    New-Item -ItemType Directory -Path $preferencesDirectory -Force | Out-Null
}
Set-Content -Path $PreferencesPath -Value $updatedLines -Encoding ASCII

$afterLines = @(Get-Content -Path $PreferencesPath)
$beforeMap = Get-PreferenceMap -Lines $beforeLines
$afterMap = Get-PreferenceMap -Lines $afterLines
$changedKeys = @(
    @("graphics_device", "compatibility", "dont_ask_graphics") |
        Where-Object { $beforeMap[$_] -ne $afterMap[$_] }
)

$summary = [pscustomobject]@{
    PreferencesPath = $PreferencesPath
    Before = [pscustomobject]@{
        GraphicsDevice = $beforeMap["graphics_device"]
        Compatibility = $beforeMap["compatibility"]
        DontAskGraphics = $beforeMap["dont_ask_graphics"]
        Entries = [pscustomobject]$beforeMap
    }
    After = [pscustomobject]@{
        GraphicsDevice = $afterMap["graphics_device"]
        Compatibility = $afterMap["compatibility"]
        DontAskGraphics = $afterMap["dont_ask_graphics"]
        Entries = [pscustomobject]$afterMap
    }
    ChangedKeys = $changedKeys
}

$json = $summary | ConvertTo-Json -Depth 6
if (-not [string]::IsNullOrWhiteSpace($SummaryOutput)) {
    $summaryDirectory = Split-Path -Parent $SummaryOutput
    if (-not [string]::IsNullOrWhiteSpace($summaryDirectory)) {
        New-Item -ItemType Directory -Path $summaryDirectory -Force | Out-Null
    }
    Set-Content -Path $SummaryOutput -Value $json -Encoding UTF8
}

$json
