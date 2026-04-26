param(
    [ValidateSet("default", "power-saving", "high-performance")]
    [string]$Preference = "power-saving",
    [string]$ControllersJsonPath = "",
    [string]$SummaryOutput = ""
)

$ErrorActionPreference = "Stop"

function Get-ControllerRecords {
    param([string]$JsonPath)

    if (-not [string]::IsNullOrWhiteSpace($JsonPath)) {
        $raw = Get-Content -Path $JsonPath -Raw -ErrorAction Stop
        $parsed = $raw | ConvertFrom-Json
        if ($parsed -is [System.Array]) {
            return @($parsed)
        }
        if ($null -ne $parsed) {
            return @($parsed)
        }
        return @()
    }

    return @(
        Get-CimInstance Win32_VideoController -ErrorAction Stop |
            Select-Object Name, AdapterCompatibility, PNPDeviceID, DriverVersion, VideoProcessor, AdapterDACType
    )
}

function Get-GraphicsDeviceId {
    param([object]$Controller)

    $pnpDeviceId = [string]$Controller.PNPDeviceID
    if ([string]::IsNullOrWhiteSpace($pnpDeviceId)) {
        return $null
    }

    if ($pnpDeviceId -match 'DEV_([0-9A-Fa-f]{4})') {
        return $Matches[1].ToLowerInvariant()
    }

    return $null
}

function Get-PreferenceScore {
    param(
        [object]$Controller,
        [string]$PreferenceName
    )

    $name = ([string]$Controller.Name).ToLowerInvariant()
    $compatibility = ([string]$Controller.AdapterCompatibility).ToLowerInvariant()
    $pnp = ([string]$Controller.PNPDeviceID).ToLowerInvariant()
    $dacType = ([string]$Controller.AdapterDACType).ToLowerInvariant()

    $isIntel = $compatibility -like "*intel*" -or $name -like "*intel*" -or $pnp -like "*ven_8086*"
    $isNvidia = $compatibility -like "*nvidia*" -or $name -like "*nvidia*" -or $pnp -like "*ven_10de*"
    $isAmd = $compatibility -like "*advanced micro devices*" -or $compatibility -like "*amd*" -or $name -like "*radeon*" -or $pnp -like "*ven_1002*"
    $isMicrosoftBasic = $name -like "*microsoft basic*" -or $compatibility -like "*microsoft*"
    $looksIntegrated = $dacType -like "*internal*" -or $name -like "*uhd*" -or $name -like "*iris*"
    $looksDiscrete = $isNvidia -or $isAmd

    switch ($PreferenceName) {
        "power-saving" {
            if ($isMicrosoftBasic) { return -100 }
            if ($isIntel -and $looksIntegrated) { return 100 }
            if ($isIntel) { return 90 }
            if ($looksIntegrated) { return 70 }
            if ($looksDiscrete) { return 20 }
            return 0
        }
        "high-performance" {
            if ($isMicrosoftBasic) { return -100 }
            if ($isNvidia) { return 100 }
            if ($isAmd) { return 95 }
            if ($looksDiscrete) { return 80 }
            if ($isIntel) { return 10 }
            return 0
        }
        default {
            return 0
        }
    }
}

$controllers = @(Get-ControllerRecords -JsonPath $ControllersJsonPath)
$candidates = @(
    foreach ($controller in $controllers) {
        $graphicsDevice = Get-GraphicsDeviceId -Controller $controller
        [pscustomobject]@{
            Name = [string]$controller.Name
            AdapterCompatibility = [string]$controller.AdapterCompatibility
            PNPDeviceID = [string]$controller.PNPDeviceID
            DriverVersion = [string]$controller.DriverVersion
            VideoProcessor = [string]$controller.VideoProcessor
            AdapterDACType = [string]$controller.AdapterDACType
            GraphicsDevice = $graphicsDevice
            PreferenceScore = Get-PreferenceScore -Controller $controller -PreferenceName $Preference
        }
    }
)

$selected = $null
if ($Preference -ne "default") {
    $selected = $candidates |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_.GraphicsDevice) } |
        Sort-Object -Property @(
            @{ Expression = "PreferenceScore"; Descending = $true },
            @{ Expression = "Name"; Descending = $false }
        ) |
        Select-Object -First 1
}

$summary = [pscustomobject]@{
    Preference = $Preference
    SelectedGraphicsDevice = if ($selected) { $selected.GraphicsDevice } else { $null }
    SelectedController = $selected
    Candidates = $candidates
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
