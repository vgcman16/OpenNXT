param(
    [int]$TargetPid = 0,
    [int]$DurationSeconds = 180,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pythonExe = "python"
$traceScript = Join-Path $PSScriptRoot "trace_rs2client_tls.py"

if ($TargetPid -le 0) {
    $process = Get-Process rs2client -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $process) {
        throw "Could not find a running rs2client.exe process"
    }
    $TargetPid = $process.Id
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $root ("data\\debug\\frida-tls\\rs2client-tls-{0}.jsonl" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
}

$outputDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

$stdoutLog = [System.IO.Path]::ChangeExtension($OutputPath, ".stdout.log")
$stderrLog = [System.IO.Path]::ChangeExtension($OutputPath, ".stderr.log")

function Quote-Argument {
    param([string]$Value)

    if ($null -eq $Value) {
        return '""'
    }

    return '"' + ($Value -replace '"', '\"') + '"'
}

$arguments = @(
    (Quote-Argument $traceScript),
    "--pid", $TargetPid,
    "--output", (Quote-Argument $OutputPath)
)

if ($DurationSeconds -gt 0) {
    $arguments += @("--duration-seconds", $DurationSeconds)
}

$process = Start-Process -FilePath $pythonExe `
    -ArgumentList $arguments `
    -WorkingDirectory $root `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

[pscustomobject]@{
    TracePid = $process.Id
    TargetPid = $TargetPid
    OutputPath = $OutputPath
    StdoutLog = $stdoutLog
    StderrLog = $stderrLog
} | ConvertTo-Json
