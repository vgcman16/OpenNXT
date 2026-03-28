param(
    [string]$Tag = "",
    [switch]$KillLauncherProcesses
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = Get-Date -Format "yyyyMMdd-HHmmss"
}

$targets = @(
    "C:\ProgramData\Jagex\RuneScape",
    (Join-Path $env:LOCALAPPDATA "Jagex\RuneScape")
)

$processNames = @("rs2client", "RuneScape")
if ($KillLauncherProcesses) {
    $processNames += "JagexLauncher"
}

Get-Process -Name $processNames -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        taskkill /PID $_.Id /F | Out-Null
    } catch {
    }
}

$results = foreach ($target in $targets) {
    if (-not (Test-Path $target)) {
        [pscustomobject]@{
            Path = $target
            Action = "missing"
            Backup = $null
        }
        continue
    }

    $parent = Split-Path -Parent $target
    $name = Split-Path -Leaf $target
    $backupName = "{0}-reset-{1}" -f $name, $Tag
    $backupPath = Join-Path $parent $backupName
    $suffix = 1
    while (Test-Path $backupPath) {
        $backupName = "{0}-reset-{1}-{2}" -f $name, $Tag, $suffix
        $backupPath = Join-Path $parent $backupName
        $suffix++
    }

    Rename-Item -Path $target -NewName $backupName
    [pscustomobject]@{
        Path = $target
        Action = "renamed"
        Backup = $backupPath
    }
}

$results | ConvertTo-Json -Depth 3
