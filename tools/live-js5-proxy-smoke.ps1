param(
    [int]$DurationSeconds = 90
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stageDir = Join-Path $root "data\debug\live-js5-proxy-client"
$proxyOutputDir = Join-Path $root "data\debug\js5-proxy-recorder-live"
$httpOut = Join-Path $root "tmp-live-proxy-http.out.log"
$httpErr = Join-Path $root "tmp-live-proxy-http.err.log"
$proxyOut = Join-Path $root "tmp-live-proxy-tool.out.log"
$proxyErr = Join-Path $root "tmp-live-proxy-tool.err.log"
$programData = "C:\ProgramData\Jagex\RuneScape"
$localData = Join-Path $env:LOCALAPPDATA "Jagex\RuneScape"
$programBackup = "${programData}_BACKUP_$timestamp"
$localBackup = "${localData}_BACKUP_$timestamp"
$renamed = @()

Get-Process -Name "JagexLauncher", "rs2client", "RuneScape", "python" -ErrorAction SilentlyContinue | ForEach-Object {
    taskkill /PID $_.Id /F | Out-Null
}

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8081, 43595 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { taskkill /PID $_ /F | Out-Null }

if (Test-Path $programData) {
    Rename-Item -Path $programData -NewName ([System.IO.Path]::GetFileName($programBackup))
    $renamed += [pscustomobject]@{ Original = $programData; Backup = $programBackup }
}

if (Test-Path $localData) {
    Rename-Item -Path $localData -NewName ([System.IO.Path]::GetFileName($localBackup))
    $renamed += [pscustomobject]@{ Original = $localData; Backup = $localBackup }
}

Remove-Item $httpOut, $httpErr, $proxyOut, $proxyErr -ErrorAction SilentlyContinue

$http = $null
$proxy = $null
$client = $null

try {
    $http = Start-Process -FilePath "python" `
        -ArgumentList "-m http.server 8081 --bind 127.0.0.1" `
        -WorkingDirectory $stageDir `
        -RedirectStandardOutput $httpOut `
        -RedirectStandardError $httpErr `
        -PassThru

    $proxy = Start-Process -FilePath (Join-Path $root "build\install\OpenNXT\bin\OpenNXT.bat") `
        -ArgumentList "run-tool js5-proxy-recorder --bind-port 43595 --remote-host content.runescape.com --remote-port 43594 --max-sessions 6 --idle-timeout-seconds 15 --session-idle-timeout-seconds 10 --output-dir `"$proxyOutputDir`"" `
        -WorkingDirectory $root `
        -RedirectStandardOutput $proxyOut `
        -RedirectStandardError $proxyErr `
        -PassThru

    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Milliseconds 500
        $ports = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -in 8081, 43595 } |
            Select-Object -ExpandProperty LocalPort -Unique |
            Sort-Object

        if (($ports -join ",") -eq "8081,43595") {
            break
        }
    }

    $client = Start-Process -FilePath (Join-Path $stageDir "rs2client.exe") `
        -ArgumentList "http://127.0.0.1:8081/jav_config.ws?binaryType=6" `
        -WorkingDirectory $stageDir `
        -PassThru

    Start-Sleep -Seconds $DurationSeconds

    $summary = Get-ChildItem $proxyOutputDir -Filter "summary-*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    $summaryJson = Get-ChildItem $proxyOutputDir -Filter "summary-*.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    [pscustomobject]@{
        Renamed = $renamed
        HttpPid = if ($http) { $http.Id } else { $null }
        ProxyPid = if ($proxy) { $proxy.Id } else { $null }
        ClientPid = if ($client) { $client.Id } else { $null }
        HttpOut = $httpOut
        HttpErr = $httpErr
        ProxyOut = $proxyOut
        ProxyErr = $proxyErr
        ProxySummary = if ($summary) { $summary.FullName } else { $null }
        ProxySummaryJson = if ($summaryJson) { $summaryJson.FullName } else { $null }
        ProxySummaryTail = if ($summary) { Get-Content $summary.FullName | Select-Object -Last 120 } else { @() }
    } | ConvertTo-Json -Depth 6
}
finally {
    if ($client) {
        taskkill /PID $client.Id /F | Out-Null
    }
    if ($proxy) {
        taskkill /PID $proxy.Id /F | Out-Null
    }
    if ($http) {
        taskkill /PID $http.Id /F | Out-Null
    }

    foreach ($entry in $renamed) {
        if (Test-Path $entry.Original) {
            Remove-Item -Path $entry.Original -Recurse -Force -ErrorAction SilentlyContinue
        }

        if (Test-Path $entry.Backup) {
            Rename-Item -Path $entry.Backup -NewName ([System.IO.Path]::GetFileName($entry.Original))
        }
    }
}
