param(
    [Parameter(Mandatory = $true)]
    [string[]]$ExecutablePath,
    [ValidateSet("default", "power-saving", "high-performance")]
    [string]$Preference = "power-saving",
    [string]$RegistryPath = "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences",
    [string]$SummaryOutput = ""
)

$ErrorActionPreference = "Stop"

function Resolve-NormalizedPath {
    param([string]$PathValue)

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $null
    }

    return [System.IO.Path]::GetFullPath($PathValue)
}

function Get-RegistryValueSafely {
    param(
        [string]$Path,
        [string]$Name
    )

    try {
        return Get-ItemPropertyValue -Path $Path -Name $Name -ErrorAction Stop
    } catch {
        return $null
    }
}

function Resolve-GpuPreferenceValue {
    param([string]$PreferenceName)

    switch ($PreferenceName) {
        "power-saving" { return "GpuPreference=1;" }
        "high-performance" { return "GpuPreference=2;" }
        default { return $null }
    }
}

$normalizedPaths = @(
    $ExecutablePath |
        ForEach-Object { Resolve-NormalizedPath -PathValue $_ } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique
)

$registryValue = Resolve-GpuPreferenceValue -PreferenceName $Preference
$entries = @()

if ($Preference -ne "default" -and -not (Test-Path $RegistryPath)) {
    New-Item -Path $RegistryPath -Force | Out-Null
}

foreach ($path in $normalizedPaths) {
    $before = if (Test-Path $RegistryPath) { Get-RegistryValueSafely -Path $RegistryPath -Name $path } else { $null }

    if ($Preference -eq "default") {
        if ($null -ne $before -and (Test-Path $RegistryPath)) {
            Remove-ItemProperty -Path $RegistryPath -Name $path -ErrorAction SilentlyContinue
        }
    } else {
        New-ItemProperty -Path $RegistryPath -Name $path -Value $registryValue -PropertyType String -Force | Out-Null
    }

    $after = if (Test-Path $RegistryPath) { Get-RegistryValueSafely -Path $RegistryPath -Name $path } else { $null }
    $entries += [pscustomobject]@{
        ExecutablePath = $path
        Exists = Test-Path $path
        Before = $before
        After = $after
        Changed = $before -ne $after
    }
}

$summary = [pscustomobject]@{
    RegistryPath = $RegistryPath
    Preference = $Preference
    Entries = $entries
    ChangedPaths = @($entries | Where-Object { $_.Changed } | Select-Object -ExpandProperty ExecutablePath)
}

$json = $summary | ConvertTo-Json -Depth 5
if (-not [string]::IsNullOrWhiteSpace($SummaryOutput)) {
    $summaryDirectory = Split-Path -Parent $SummaryOutput
    if (-not [string]::IsNullOrWhiteSpace($summaryDirectory)) {
        New-Item -ItemType Directory -Path $summaryDirectory -Force | Out-Null
    }
    Set-Content -Path $SummaryOutput -Value $json -Encoding UTF8
}

$json
