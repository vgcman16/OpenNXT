param(
    [ValidateSet("Switch", "Use Default Settings", "No")]
    [string]$Action = "Switch",
    [int]$TimeoutSeconds = 45,
    [string]$SummaryOutput = ""
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$root = Split-Path -Parent $PSScriptRoot

function Get-TrackedFileSnapshot {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return [pscustomobject]@{
            Path = $Path
            Exists = $false
            Length = 0
            LastWriteTimeUtc = $null
            Sha256 = $null
        }
    }

    $item = Get-Item $Path
    $hash = $null
    $hashReadError = $null
    try {
        $hash = (Get-FileHash -Path $Path -Algorithm SHA256 -ErrorAction Stop).Hash
    } catch {
        $hashReadError = $_.Exception.Message
    }
    return [pscustomobject]@{
        Path = $item.FullName
        Exists = $true
        Length = [int64]$item.Length
        LastWriteTimeUtc = $item.LastWriteTimeUtc.ToString("o")
        Sha256 = $hash
        Sha256ReadError = $hashReadError
    }
}

function Get-RegTreeSnapshot {
    param([string]$RegistryPath)

    if (-not (Test-Path $RegistryPath)) {
        return @()
    }

    $results = New-Object System.Collections.Generic.List[object]
    $keys = @(Get-Item $RegistryPath)
    $keys += @(Get-ChildItem -Path $RegistryPath -Recurse -ErrorAction SilentlyContinue)
    foreach ($key in $keys) {
        $propertyNames = $key.GetValueNames()
        if ($null -eq $propertyNames -or $propertyNames.Count -eq 0) {
            $results.Add([pscustomobject]@{
                Key = $key.Name
                Name = ""
                Value = $null
            })
            continue
        }

        foreach ($propertyName in $propertyNames) {
            $displayName = if ([string]::IsNullOrEmpty($propertyName)) { "(Default)" } else { $propertyName }
            $results.Add([pscustomobject]@{
                Key = $key.Name
                Name = $displayName
                Value = $key.GetValue($propertyName)
            })
        }
    }

    return $results
}

function Get-StateSnapshot {
    $trackedFiles = @(
        "C:\ProgramData\Jagex\launcher\preferences.cfg",
        "C:\ProgramData\Jagex\RuneScape\GlobalSettings.jcache",
        "C:\Users\Demon\AppData\Local\Jagex\RuneScape\Settings.jcache"
    )

    return [pscustomobject]@{
        TimestampUtc = (Get-Date).ToUniversalTime().ToString("o")
        Files = @($trackedFiles | ForEach-Object { Get-TrackedFileSnapshot -Path $_ })
        Registry = @(Get-RegTreeSnapshot -RegistryPath "HKCU:\Software\Jagex\RuneScape")
    }
}

function Find-GraphicsErrorDialog {
    $rootElement = [System.Windows.Automation.AutomationElement]::RootElement
    if ($null -eq $rootElement) {
        return $null
    }

    $windowCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Window
    )
    $windows = $rootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $windowCondition)
    foreach ($window in $windows) {
        try {
            $windowName = $window.Current.Name
            $className = $window.Current.ClassName
        } catch {
            continue
        }

        $allDescendants = $window.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        $texts = @()
        $buttonNames = @()
        foreach ($element in $allDescendants) {
            try {
                $name = $element.Current.Name
                $controlType = $element.Current.ControlType.ProgrammaticName
            } catch {
                continue
            }
            if (-not [string]::IsNullOrWhiteSpace($name)) {
                $texts += $name
                if ($controlType -eq "ControlType.Button") {
                    $buttonNames += $name
                }
            }
        }

        $textBlob = ($texts -join "`n")
        $hasExpectedButtons = (
            ($buttonNames -contains "Switch") -and
            ($buttonNames -contains "No") -and
            ($buttonNames -contains "Use Default Settings")
        )
        if (
            $hasExpectedButtons -and
            (
                $windowName -eq "Error" -or
                $className -eq "#32770" -or
                $textBlob -like "*RuneScape client suffered from an error*" -or
                $textBlob -like "*graphics initialisation*" -or
                $textBlob -like "*graphics driver issues*"
            )
        ) {
            return [pscustomobject]@{
                Window = $window
                Texts = $texts
                ButtonNames = $buttonNames
            }
        }
    }

    return $null
}

function Invoke-DialogButton {
    param(
        [System.Windows.Automation.AutomationElement]$Window,
        [string]$ButtonName
    )

    $buttonCondition = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Button
        )),
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            $ButtonName
        ))
    )

    $button = $Window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
    if ($null -eq $button) {
        return $false
    }

    $pattern = $null
    if (-not $button.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
        return $false
    }

    ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
    return $true
}

function Get-FileDiff {
    param(
        [object[]]$Before,
        [object[]]$After
    )

    $beforeMap = @{}
    foreach ($entry in $Before) {
        $beforeMap[$entry.Path] = $entry
    }

    $diffs = New-Object System.Collections.Generic.List[object]
    foreach ($entry in $After) {
        $previous = $beforeMap[$entry.Path]
        if (
            $null -eq $previous -or
            $previous.Exists -ne $entry.Exists -or
            $previous.Length -ne $entry.Length -or
            $previous.LastWriteTimeUtc -ne $entry.LastWriteTimeUtc -or
            $previous.Sha256 -ne $entry.Sha256
        ) {
            $diffs.Add([pscustomobject]@{
                Path = $entry.Path
                BeforeExists = if ($previous) { $previous.Exists } else { $null }
                AfterExists = $entry.Exists
                BeforeLength = if ($previous) { $previous.Length } else { $null }
                AfterLength = $entry.Length
                BeforeLastWriteTimeUtc = if ($previous) { $previous.LastWriteTimeUtc } else { $null }
                AfterLastWriteTimeUtc = $entry.LastWriteTimeUtc
                BeforeSha256 = if ($previous) { $previous.Sha256 } else { $null }
                AfterSha256 = $entry.Sha256
            })
        }
    }

    return $diffs
}

function Get-RegistryDiff {
    param(
        [object[]]$Before,
        [object[]]$After
    )

    $beforeMap = @{}
    foreach ($entry in $Before) {
        $beforeMap["$($entry.Key)|$($entry.Name)"] = $entry.Value
    }

    $diffs = New-Object System.Collections.Generic.List[object]
    foreach ($entry in $After) {
        $mapKey = "$($entry.Key)|$($entry.Name)"
        $previous = $beforeMap[$mapKey]
        if ($previous -ne $entry.Value) {
            $diffs.Add([pscustomobject]@{
                Key = $entry.Key
                Name = $entry.Name
                BeforeValue = $previous
                AfterValue = $entry.Value
            })
        }
    }

    return $diffs
}

$beforeSnapshot = Get-StateSnapshot
$deadline = (Get-Date).AddSeconds([Math]::Max(1, $TimeoutSeconds))
$detectedTexts = @()
$detectedButtons = @()
$invoked = $false

do {
    $dialog = Find-GraphicsErrorDialog
    if ($null -ne $dialog) {
        $detectedTexts = $dialog.Texts
        $detectedButtons = $dialog.ButtonNames
        $invoked = Invoke-DialogButton -Window $dialog.Window -ButtonName $Action
        if ($invoked) {
            break
        }
    }

    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)

Start-Sleep -Milliseconds 750
$afterSnapshot = Get-StateSnapshot

$summary = [pscustomobject]@{
    Action = $Action
    Invoked = $invoked
    TimeoutSeconds = $TimeoutSeconds
    DetectedTexts = $detectedTexts
    DetectedButtons = $detectedButtons
    Before = $beforeSnapshot
    After = $afterSnapshot
    FileDiff = @(Get-FileDiff -Before $beforeSnapshot.Files -After $afterSnapshot.Files)
    RegistryDiff = @(Get-RegistryDiff -Before $beforeSnapshot.Registry -After $afterSnapshot.Registry)
}

$json = $summary | ConvertTo-Json -Depth 8
if (-not [string]::IsNullOrWhiteSpace($SummaryOutput)) {
    $summaryDirectory = Split-Path -Parent $SummaryOutput
    if (-not [string]::IsNullOrWhiteSpace($summaryDirectory)) {
        New-Item -ItemType Directory -Path $summaryDirectory -Force | Out-Null
    }
    Set-Content -Path $SummaryOutput -Value $json -Encoding UTF8
}

$json
